#include "calibration.hpp"

#include "driver_log.hpp"

#include <cmath>
#include <cstdlib>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <system_error>

namespace uts
{

namespace
{

Quat Multiply(const Quat &a, const Quat &b)
{
    return {
        a.w * b.x + a.x * b.w + a.y * b.z - a.z * b.y,
        a.w * b.y - a.x * b.z + a.y * b.w + a.z * b.x,
        a.w * b.z + a.x * b.y - a.y * b.x + a.z * b.w,
        a.w * b.w - a.x * b.x - a.y * b.y - a.z * b.z,
    };
}

Vec3 Rotate(const Quat &q, const Vec3 &v)
{
    // v' = q * (v, 0) * conj(q)
    const Quat p {v.x, v.y, v.z, 0.0};
    const Quat conj {-q.x, -q.y, -q.z, q.w};
    const Quat r = Multiply(Multiply(q, p), conj);
    return {r.x, r.y, r.z};
}

} // namespace

Calibration Calibration::Identity()
{
    return {};
}

bool Calibration::Parse(const std::string &text, Calibration &out)
{
    std::istringstream stream(text);
    std::string tag;
    int version = 0;
    double v[7];
    if (!(stream >> tag >> version) || tag != "CALIBRATION" || version != 1)
    {
        return false;
    }
    for (double &value : v)
    {
        if (!(stream >> value) || !std::isfinite(value))
        {
            return false;
        }
    }
    std::string extra;
    if (stream >> extra)
    {
        return false;
    }

    const double norm = std::sqrt(v[3] * v[3] + v[4] * v[4] + v[5] * v[5] + v[6] * v[6]);
    if (norm < 1e-6)
    {
        return false;
    }

    out.translation_m = {v[0], v[1], v[2]};
    out.rotation = {v[3] / norm, v[4] / norm, v[5] / norm, v[6] / norm};
    return true;
}

void Calibration::Apply(TrackedPose &pose) const
{
    const Vec3 rotated = Rotate(rotation, pose.position_m);
    pose.position_m = {rotated.x + translation_m.x, rotated.y + translation_m.y, rotated.z + translation_m.z};
    pose.orientation_xyzw = Multiply(rotation, pose.orientation_xyzw);
    pose.linear_accel_m_s2 = Rotate(rotation, pose.linear_accel_m_s2);
}

CalibrationFile::CalibrationFile(std::string path) : path_(std::move(path)) {}

const std::string &CalibrationFile::path() const
{
    return path_;
}

const Calibration &CalibrationFile::current() const
{
    return current_;
}

bool CalibrationFile::Refresh()
{
    namespace fs = std::filesystem;
    std::error_code ec;
    const auto mtime = fs::last_write_time(path_, ec);
    if (ec)
    {
        if (last_mtime_ns_ != -1)
        {
            Logf("calibration file %s disappeared, keeping last value", path_.c_str());
            last_mtime_ns_ = -1;
        }
        return false;
    }

    const long long mtime_ns =
        std::chrono::duration_cast<std::chrono::nanoseconds>(mtime.time_since_epoch()).count();
    if (mtime_ns == last_mtime_ns_)
    {
        return false;
    }
    last_mtime_ns_ = mtime_ns;

    std::ifstream in(path_);
    std::string line;
    Calibration parsed;
    while (std::getline(in, line))
    {
        if (!line.empty() && line[0] != '#')
        {
            if (Calibration::Parse(line, parsed))
            {
                current_ = parsed;
                Logf("loaded calibration from %s", path_.c_str());
                return true;
            }
            break;
        }
    }
    Logf("ignoring invalid calibration in %s", path_.c_str());
    return false;
}

std::string DefaultCalibrationPath()
{
    if (const char *env = std::getenv("ULTIMATE_TRACKER_CALIBRATION"); env != nullptr && env[0] != '\0')
    {
        return env;
    }
    if (const char *xdg = std::getenv("XDG_CONFIG_HOME"); xdg != nullptr && xdg[0] != '\0')
    {
        return std::string(xdg) + "/ultimate-tracker/calibration.txt";
    }
#ifdef _WIN32
    if (const char *appdata = std::getenv("APPDATA"); appdata != nullptr && appdata[0] != '\0')
    {
        return std::string(appdata) + "\\ultimate-tracker\\calibration.txt";
    }
#endif
    const char *home = std::getenv("HOME");
    return std::string(home != nullptr ? home : ".") + "/.config/ultimate-tracker/calibration.txt";
}

} // namespace uts
