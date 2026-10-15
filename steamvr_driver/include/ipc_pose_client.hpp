#pragma once

#include "pose_types.hpp"

#include <cstdint>
#include <functional>
#include <string>

namespace uts
{

// Where the pose daemon listens: `unix:/path` (or a bare path) or `tcp:<loopback-ip>:<port>`.
// Loopback only, mirroring python/pose_daemon endpoint.py; see protocol/pose-v1.md.
struct Endpoint
{
    enum class Kind
    {
        Unix,
        Tcp
    };
    Kind kind = Kind::Unix;
    std::string path;
    std::string host;
    int port = 0;
};

// Returns false for malformed specs and for tcp hosts that are not loopback addresses.
bool ParseEndpoint(const std::string &spec, Endpoint &out);
// $ULTIMATE_TRACKER_SOCKET_PATH, else tcp:127.0.0.1:38450 on Windows and the /tmp Unix socket elsewhere.
std::string DefaultEndpointSpec();

class IpcPoseClient
{
  public:
    explicit IpcPoseClient(std::string socket_path);
    ~IpcPoseClient();

    void SetSocketPath(std::string socket_path);
    const std::string &SocketPath() const;
    bool Connect();
    void Disconnect();
    bool IsConnected() const;

    struct Handlers
    {
        std::function<void(const TrackedPose &)> on_pose;
        std::function<void(const BatteryStatus &)> on_battery;
        std::function<void(const ButtonState &)> on_buttons;
    };

    void Poll(const Handlers &handlers);
    void Poll(const std::function<void(const TrackedPose &)> &on_pose);

    // Parses one `POSE 1|2 ...` line (see protocol/pose-v1.md). Returns false on any malformed
    // or non-finite input, leaving `out_pose` unspecified.
    static bool ParsePoseLine(const std::string &line, TrackedPose &out_pose);
    // `BATTERY 1 <serial> <percent 0-100> <charging 0|1>` and `BUTTONS 1 <serial> <mask 0-31>`.
    // `HAPTIC 1 <serial> <duration_s> <frequency_hz> <amplitude>` (driver to daemon). Values are clamped to the
    // protocol ranges; returns false for non-finite numbers or a serial containing whitespace.
    static bool FormatHapticLine(const HapticPulse &pulse, std::string &out_line);
    // Best effort: returns false when not connected or the socket cannot take the line right now.
    bool SendHaptic(const HapticPulse &pulse);
    static bool ParseBatteryLine(const std::string &line, BatteryStatus &out);
    static bool ParseButtonsLine(const std::string &line, ButtonState &out);

  private:

    std::string socket_path_;
    std::intptr_t socket_fd_ = -1;
    std::string read_buffer_;
};

} // namespace uts
