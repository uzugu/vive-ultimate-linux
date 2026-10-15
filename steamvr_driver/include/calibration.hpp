#pragma once

#include "pose_types.hpp"

#include <string>

namespace uts
{

// Rigid transform T_steamvr_from_vut: p' = R * p + t, q' = R * q (Hamilton product, xyzw fields).
// See protocol/pose-v1.md ("Calibration boundary") and docs/calibration.md.
struct Calibration
{
    Vec3 translation_m;
    Quat rotation; // unit quaternion

    static Calibration Identity();

    // Parses `CALIBRATION 1 tx ty tz qx qy qz qw`. The quaternion is normalised; zero-length, non-finite
    // or malformed input returns false and leaves `out` unchanged.
    static bool Parse(const std::string &text, Calibration &out);

    void Apply(TrackedPose &pose) const;
};

// Calibration read from a file that may change while SteamVR runs (a calibration tool rewrites it).
class CalibrationFile
{
  public:
    explicit CalibrationFile(std::string path);

    const std::string &path() const;
    // Re-reads the file if its modification time changed. A missing file keeps the identity; a broken
    // file keeps the last good value. Returns true if the value changed.
    bool Refresh();
    const Calibration &current() const;

  private:
    std::string path_;
    long long last_mtime_ns_ = -1;
    Calibration current_ = Calibration::Identity();
};

// Default location: $ULTIMATE_TRACKER_CALIBRATION, else $XDG_CONFIG_HOME or ~/.config /ultimate-tracker/calibration.txt
std::string DefaultCalibrationPath();

} // namespace uts
