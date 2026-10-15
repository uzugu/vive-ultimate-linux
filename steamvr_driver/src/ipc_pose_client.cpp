#include "ipc_pose_client.hpp"

#include "driver_log.hpp"

#include <cerrno>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <sstream>
#include <string>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

namespace uts
{

namespace
{
constexpr std::size_t kMaxBufferedBytes = 1 << 20;
} // namespace

IpcPoseClient::IpcPoseClient(std::string socket_path) : socket_path_(std::move(socket_path)) {}

IpcPoseClient::~IpcPoseClient()
{
    Disconnect();
}

void IpcPoseClient::SetSocketPath(std::string socket_path)
{
    if (socket_path_ == socket_path)
    {
        return;
    }

    Disconnect();
    socket_path_ = std::move(socket_path);
}

const std::string &IpcPoseClient::SocketPath() const
{
    return socket_path_;
}

bool IpcPoseClient::Connect()
{
    if (socket_fd_ >= 0)
    {
        return true;
    }

    socket_fd_ = ::socket(AF_UNIX, SOCK_STREAM | SOCK_NONBLOCK, 0);
    if (socket_fd_ < 0)
    {
        Logf("failed to create Unix socket: %s", std::strerror(errno));
        return false;
    }

    sockaddr_un addr {};
    addr.sun_family = AF_UNIX;
    std::snprintf(addr.sun_path, sizeof(addr.sun_path), "%s", socket_path_.c_str());

    const int rc = ::connect(socket_fd_, reinterpret_cast<sockaddr *>(&addr), sizeof(addr));
    if (rc < 0 && errno != EINPROGRESS)
    {
        Logf("failed to connect to %s: %s", socket_path_.c_str(), std::strerror(errno));
        Disconnect();
        return false;
    }

    return true;
}

void IpcPoseClient::Disconnect()
{
    if (socket_fd_ >= 0)
    {
        ::close(socket_fd_);
        socket_fd_ = -1;
    }
    read_buffer_.clear();
}

bool IpcPoseClient::IsConnected() const
{
    return socket_fd_ >= 0;
}

void IpcPoseClient::Poll(const std::function<void(const TrackedPose &)> &on_pose)
{
    Handlers handlers;
    handlers.on_pose = on_pose;
    Poll(handlers);
}

void IpcPoseClient::Poll(const Handlers &handlers)
{
    if (!IsConnected() && !Connect())
    {
        return;
    }

    char buffer[4096];
    while (true)
    {
        const ssize_t nread = ::read(socket_fd_, buffer, sizeof(buffer));
        if (nread > 0)
        {
            read_buffer_.append(buffer, static_cast<std::size_t>(nread));
            if (read_buffer_.size() > kMaxBufferedBytes && read_buffer_.find('\n') == std::string::npos)
            {
                Logf("pose socket sent %zu bytes without a newline, dropping connection", read_buffer_.size());
                Disconnect();
                return;
            }
            continue;
        }

        if (nread == 0)
        {
            Logf("pose daemon disconnected");
            Disconnect();
            return;
        }

        if (errno != EAGAIN && errno != EWOULDBLOCK)
        {
            Logf("read error on pose socket: %s", std::strerror(errno));
            Disconnect();
            return;
        }

        break;
    }

    std::size_t line_end = 0;
    while ((line_end = read_buffer_.find('\n')) != std::string::npos)
    {
        std::string line = read_buffer_.substr(0, line_end);
        read_buffer_.erase(0, line_end + 1);

        // Unknown tags are ignored on purpose: newer daemons may send message types this driver predates.
        if (line.compare(0, 5, "POSE ") == 0)
        {
            TrackedPose pose;
            if (handlers.on_pose && ParsePoseLine(line, pose))
            {
                handlers.on_pose(pose);
            }
        }
        else if (line.compare(0, 8, "BATTERY ") == 0)
        {
            BatteryStatus battery;
            if (handlers.on_battery && ParseBatteryLine(line, battery))
            {
                handlers.on_battery(battery);
            }
        }
        else if (line.compare(0, 8, "BUTTONS ") == 0)
        {
            ButtonState buttons;
            if (handlers.on_buttons && ParseButtonsLine(line, buttons))
            {
                handlers.on_buttons(buttons);
            }
        }
    }
}

bool IpcPoseClient::ParsePoseLine(const std::string &line, TrackedPose &out_pose)
{
    std::istringstream stream(line);
    std::string tag;
    int version = 0;
    long long timestamp_ns = 0;

    if (!(stream >> tag >> version))
    {
        return false;
    }

    if (tag != "POSE" || (version != 1 && version != 2))
    {
        return false;
    }

    if (!(stream >> out_pose.tracker_index >> out_pose.serial >> out_pose.status >>
          out_pose.position_m.x >> out_pose.position_m.y >> out_pose.position_m.z >>
          out_pose.orientation_xyzw.x >> out_pose.orientation_xyzw.y >> out_pose.orientation_xyzw.z >>
          out_pose.orientation_xyzw.w >> out_pose.linear_accel_m_s2.x >> out_pose.linear_accel_m_s2.y >>
          out_pose.linear_accel_m_s2.z >> timestamp_ns) ||
        timestamp_ns < 0)
    {
        return false;
    }
    out_pose.timestamp_ns = static_cast<std::uint64_t>(timestamp_ns);

    if (version == 2)
    {
        if (!(stream >> out_pose.tracking_code >> out_pose.tracking_label))
        {
            return false;
        }
    }

    // Trailing garbage means the line does not follow the protocol.
    std::string extra;
    if (stream >> extra)
    {
        return false;
    }

    const double values[] = {out_pose.position_m.x,         out_pose.position_m.y,         out_pose.position_m.z,
                             out_pose.orientation_xyzw.x,   out_pose.orientation_xyzw.y,   out_pose.orientation_xyzw.z,
                             out_pose.orientation_xyzw.w,   out_pose.linear_accel_m_s2.x,  out_pose.linear_accel_m_s2.y,
                             out_pose.linear_accel_m_s2.z};
    for (const double value : values)
    {
        if (!std::isfinite(value))
        {
            return false;
        }
    }

    return true;
}

bool IpcPoseClient::ParseBatteryLine(const std::string &line, BatteryStatus &out)
{
    std::istringstream stream(line);
    std::string tag, extra;
    int version = 0, charging = 0;
    BatteryStatus parsed;
    if (!(stream >> tag >> version >> parsed.serial >> parsed.percent >> charging) || tag != "BATTERY" || version != 1 ||
        (stream >> extra) || parsed.percent < 0 || parsed.percent > 100 || (charging != 0 && charging != 1))
    {
        return false;
    }
    parsed.charging = charging == 1;
    out = parsed;
    return true;
}

bool IpcPoseClient::ParseButtonsLine(const std::string &line, ButtonState &out)
{
    std::istringstream stream(line);
    std::string tag, extra;
    int version = 0;
    ButtonState parsed;
    if (!(stream >> tag >> version >> parsed.serial >> parsed.mask) || tag != "BUTTONS" || version != 1 ||
        (stream >> extra) || parsed.mask < 0 || parsed.mask > kButtonAll)
    {
        return false;
    }
    out = parsed;
    return true;
}

} // namespace uts
