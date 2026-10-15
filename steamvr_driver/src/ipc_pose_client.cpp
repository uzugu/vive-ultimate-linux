#include "ipc_pose_client.hpp"

#include "driver_log.hpp"

#include <cerrno>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <sstream>
#include <string>

#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#else
#include <arpa/inet.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#endif

namespace uts
{

namespace
{
constexpr std::size_t kMaxBufferedBytes = 1 << 20;

#ifdef _WIN32
using NativeSocket = SOCKET;
const NativeSocket kInvalid = INVALID_SOCKET;
int LastError() { return WSAGetLastError(); }
bool WouldBlock(int e) { return e == WSAEWOULDBLOCK; }
void CloseSocket(NativeSocket s) { ::closesocket(s); }
bool SetNonBlocking(NativeSocket s)
{
    u_long mode = 1;
    return ::ioctlsocket(s, FIONBIO, &mode) == 0;
}
std::string ErrorText(int e) { return "winsock error " + std::to_string(e); }
void EnsureWinsock()
{
    static const bool started = [] {
        WSADATA data;
        return ::WSAStartup(MAKEWORD(2, 2), &data) == 0;
    }();
    (void)started;
}
constexpr int kSendFlags = 0;
#else
using NativeSocket = int;
const NativeSocket kInvalid = -1;
int LastError() { return errno; }
bool WouldBlock(int e) { return e == EAGAIN || e == EWOULDBLOCK; }
void CloseSocket(NativeSocket s) { ::close(s); }
bool SetNonBlocking(NativeSocket s)
{
    const int flags = ::fcntl(s, F_GETFL, 0);
    return flags >= 0 && ::fcntl(s, F_SETFL, flags | O_NONBLOCK) == 0;
}
std::string ErrorText(int e) { return std::strerror(e); }
void EnsureWinsock() {}
// MSG_NOSIGNAL: a vanished daemon must not kill vrserver with SIGPIPE.
constexpr int kSendFlags = MSG_NOSIGNAL;
#endif

NativeSocket ToNative(std::intptr_t fd) { return static_cast<NativeSocket>(fd); }

bool ParsePort(const std::string &text, int &port)
{
    if (text.empty() || text.size() > 5 || text.find_first_not_of("0123456789") != std::string::npos)
    {
        return false;
    }
    port = std::atoi(text.c_str());
    return port >= 1 && port <= 65535;
}

bool IsLoopback(const std::string &host)
{
    in_addr v4 {};
    if (::inet_pton(AF_INET, host.c_str(), &v4) == 1)
    {
        return (ntohl(v4.s_addr) >> 24) == 127;
    }
    return host == "::1";
}
} // namespace

bool ParseEndpoint(const std::string &spec, Endpoint &out)
{
    Endpoint parsed;
    if (spec.compare(0, 4, "tcp:") == 0)
    {
        const std::string rest = spec.substr(4);
        const std::size_t colon = rest.rfind(':');
        if (colon == std::string::npos || colon == 0)
        {
            return false;
        }
        parsed.kind = Endpoint::Kind::Tcp;
        parsed.host = rest.substr(0, colon);
        if (!ParsePort(rest.substr(colon + 1), parsed.port) || !IsLoopback(parsed.host))
        {
            return false;
        }
    }
    else
    {
        parsed.kind = Endpoint::Kind::Unix;
        parsed.path = spec.compare(0, 5, "unix:") == 0 ? spec.substr(5) : spec;
        if (parsed.path.empty())
        {
            return false;
        }
    }
    out = parsed;
    return true;
}

std::string DefaultEndpointSpec()
{
    if (const char *env = std::getenv("ULTIMATE_TRACKER_SOCKET_PATH"); env != nullptr && env[0] != '\0')
    {
        return env;
    }
#ifdef _WIN32
    return "tcp:127.0.0.1:38450";
#else
    return "/tmp/ultimate-tracker-linux.sock";
#endif
}

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

    Endpoint endpoint;
    if (!ParseEndpoint(socket_path_, endpoint))
    {
        Logf("invalid pose endpoint '%s'", socket_path_.c_str());
        return false;
    }
    EnsureWinsock();

    NativeSocket fd = kInvalid;
    int rc = -1;
    if (endpoint.kind == Endpoint::Kind::Tcp)
    {
        const bool v6 = endpoint.host.find(':') != std::string::npos;
        fd = ::socket(v6 ? AF_INET6 : AF_INET, SOCK_STREAM, 0);
        if (fd == kInvalid)
        {
            Logf("failed to create TCP socket: %s", ErrorText(LastError()).c_str());
            return false;
        }
        // Loopback connects finish (or are refused) immediately, so connect blocking and switch afterwards.
        if (v6)
        {
            sockaddr_in6 addr {};
            addr.sin6_family = AF_INET6;
            addr.sin6_port = htons(static_cast<unsigned short>(endpoint.port));
            ::inet_pton(AF_INET6, endpoint.host.c_str(), &addr.sin6_addr);
            rc = ::connect(fd, reinterpret_cast<sockaddr *>(&addr), sizeof(addr));
        }
        else
        {
            sockaddr_in addr {};
            addr.sin_family = AF_INET;
            addr.sin_port = htons(static_cast<unsigned short>(endpoint.port));
            ::inet_pton(AF_INET, endpoint.host.c_str(), &addr.sin_addr);
            rc = ::connect(fd, reinterpret_cast<sockaddr *>(&addr), sizeof(addr));
        }
        if (rc == 0)
        {
            const int one = 1;
            ::setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, reinterpret_cast<const char *>(&one), sizeof(one));
        }
    }
    else
    {
#ifdef _WIN32
        Logf("unix endpoints are not supported on Windows: %s", socket_path_.c_str());
        return false;
#else
        fd = ::socket(AF_UNIX, SOCK_STREAM, 0);
        if (fd == kInvalid)
        {
            Logf("failed to create Unix socket: %s", ErrorText(LastError()).c_str());
            return false;
        }
        sockaddr_un addr {};
        addr.sun_family = AF_UNIX;
        std::snprintf(addr.sun_path, sizeof(addr.sun_path), "%s", endpoint.path.c_str());
        rc = ::connect(fd, reinterpret_cast<sockaddr *>(&addr), sizeof(addr));
#endif
    }

    if (rc != 0 || !SetNonBlocking(fd))
    {
        Logf("failed to connect to %s: %s", socket_path_.c_str(), ErrorText(LastError()).c_str());
        CloseSocket(fd);
        return false;
    }

    socket_fd_ = static_cast<std::intptr_t>(fd);
    return true;
}

void IpcPoseClient::Disconnect()
{
    if (socket_fd_ >= 0)
    {
        CloseSocket(ToNative(socket_fd_));
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
        const int nread = static_cast<int>(::recv(ToNative(socket_fd_), buffer, sizeof(buffer), 0));
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

        const int error = LastError();
        if (!WouldBlock(error))
        {
            Logf("read error on pose socket: %s", ErrorText(error).c_str());
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
        else if (line.compare(0, 6, "HELLO ") == 0)
        {
            HelloInfo hello;
            if (handlers.on_hello && ParseHelloLine(line, hello))
            {
                handlers.on_hello(hello);
            }
        }
        else if (line.compare(0, 7, "DEVICE ") == 0)
        {
            DeviceInfo device;
            if (handlers.on_device && ParseDeviceLine(line, device))
            {
                handlers.on_device(device);
            }
        }
        else if (line.compare(0, 6, "EVENT ") == 0)
        {
            EventInfo event;
            if (handlers.on_event && ParseEventLine(line, event))
            {
                handlers.on_event(event);
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

bool IpcPoseClient::FormatHapticLine(const HapticPulse &pulse, std::string &out_line)
{
    if (pulse.serial.empty() || pulse.serial.find_first_of(" \t\r\n") != std::string::npos ||
        !std::isfinite(pulse.duration_s) || !std::isfinite(pulse.frequency_hz) || !std::isfinite(pulse.amplitude))
    {
        return false;
    }
    const double duration = std::fmin(std::fmax(pulse.duration_s, 0.0), 10.0);
    const double frequency = std::fmin(std::fmax(pulse.frequency_hz, 0.0), 1000.0);
    const double amplitude = std::fmin(std::fmax(pulse.amplitude, 0.0), 1.0);
    char buffer[64];
    std::snprintf(buffer, sizeof(buffer), " %.4f %.2f %.4f\n", duration, frequency, amplitude);
    out_line = "HAPTIC 1 " + pulse.serial + buffer;
    return true;
}

bool IpcPoseClient::SendHaptic(const HapticPulse &pulse)
{
    std::string line;
    if (!IsConnected() || !FormatHapticLine(pulse, line))
    {
        return false;
    }
    // The socket is non-blocking, so a full buffer drops the pulse instead of stalling vrserver.
    const auto sent = ::send(ToNative(socket_fd_), line.data(), static_cast<int>(line.size()), kSendFlags);
    return sent == static_cast<decltype(sent)>(line.size());
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

namespace
{
bool ValidKind(const std::string &kind)
{
    if (kind.empty() || kind.size() > 32 || !(kind[0] >= 'a' && kind[0] <= 'z'))
    {
        return false;
    }
    for (const char ch : kind)
    {
        if (!((ch >= 'a' && ch <= 'z') || (ch >= '0' && ch <= '9') || ch == '_'))
        {
            return false;
        }
    }
    return true;
}
} // namespace

bool IpcPoseClient::ParseHelloLine(const std::string &line, HelloInfo &out)
{
    std::istringstream stream(line);
    std::string tag, extra;
    int version = 0;
    HelloInfo parsed;
    if (!(stream >> tag >> version >> parsed.daemon_version >> parsed.source) || tag != "HELLO" || version != 1 ||
        (stream >> extra) || parsed.daemon_version.size() > 64 || parsed.source.size() > 64)
    {
        return false;
    }
    out = parsed;
    return true;
}

bool IpcPoseClient::ParseDeviceLine(const std::string &line, DeviceInfo &out)
{
    std::istringstream stream(line);
    std::string tag, extra;
    int version = 0, connected = 0;
    DeviceInfo parsed;
    if (!(stream >> tag >> version >> parsed.serial >> parsed.tracker_index >> connected) || tag != "DEVICE" ||
        version != 1 || (stream >> extra) || parsed.tracker_index < 0 || (connected != 0 && connected != 1) ||
        parsed.serial.size() > 64)
    {
        return false;
    }
    parsed.connected = connected == 1;
    out = parsed;
    return true;
}

bool IpcPoseClient::ParseEventLine(const std::string &line, EventInfo &out)
{
    std::istringstream stream(line);
    std::string tag, extra, serial, detail;
    int version = 0;
    EventInfo parsed;
    if (!(stream >> tag >> version >> parsed.kind >> serial >> detail) || tag != "EVENT" || version != 1 ||
        (stream >> extra) || !ValidKind(parsed.kind) || serial.size() > 64 || detail.size() > 64)
    {
        return false;
    }
    parsed.serial = serial == "-" ? "" : serial;
    parsed.detail = detail == "-" ? "" : detail;
    out = parsed;
    return true;
}

} // namespace uts
