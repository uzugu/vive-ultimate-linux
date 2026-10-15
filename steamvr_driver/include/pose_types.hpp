#pragma once

#include <cstdint>
#include <string>

namespace uts
{

struct Vec3
{
    double x = 0.0;
    double y = 0.0;
    double z = 0.0;
};

struct Quat
{
    double x = 0.0;
    double y = 0.0;
    double z = 0.0;
    double w = 1.0;
};

struct TrackedPose
{
    int tracker_index = 0;
    std::string serial;
    std::string status = "searching";
    int tracking_code = -999;
    std::string tracking_label = "unknown";
    Vec3 position_m;
    Quat orientation_xyzw;
    Vec3 linear_accel_m_s2;
    std::uint64_t timestamp_ns = 0;
};

// Button bits in ButtonState::mask (HTC order: system button, grip, trigger, trackpad, menu).
enum ButtonBit : int
{
    kButtonPower = 1,
    kButtonGrip = 2,
    kButtonTrigger = 4,
    kButtonTrackpad = 8,
    kButtonMenu = 16,
    kButtonAll = 31,
};

struct BatteryStatus
{
    std::string serial;
    int percent = 0;
    bool charging = false;
};

struct ButtonState
{
    std::string serial;
    int mask = 0;
};

// Daemon to client metadata (see protocol/pose-v1.md): HELLO, DEVICE and EVENT.
struct HelloInfo
{
    std::string daemon_version;
    std::string source;
};

struct DeviceInfo
{
    std::string serial;
    int tracker_index = 0;
    bool connected = false;
};

struct EventInfo
{
    std::string kind;
    std::string serial; // empty when the event is not about one tracker
    std::string detail; // empty when there is none
};

struct HapticPulse
{
    std::string serial;
    double duration_s = 0.0;
    double frequency_hz = 0.0;
    double amplitude = 0.0;
};

} // namespace uts
