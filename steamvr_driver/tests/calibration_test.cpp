#include "calibration.hpp"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>
#include <thread>
#include <chrono>
#include <unistd.h>

namespace
{

int g_failures = 0;

#define CHECK(cond)                                                                        \
    do                                                                                     \
    {                                                                                      \
        if (!(cond))                                                                       \
        {                                                                                  \
            std::fprintf(stderr, "%s:%d: CHECK failed: %s\n", __FILE__, __LINE__, #cond); \
            ++g_failures;                                                                  \
        }                                                                                  \
    } while (0)

bool Near(double a, double b)
{
    return std::fabs(a - b) < 1e-9;
}

uts::TrackedPose MakePose()
{
    uts::TrackedPose pose;
    pose.position_m = {1.0, 0.5, 0.0};
    pose.linear_accel_m_s2 = {1.0, 0.0, 0.0};
    return pose;
}

void TestIdentity()
{
    auto pose = MakePose();
    uts::Calibration::Identity().Apply(pose);
    CHECK(Near(pose.position_m.x, 1.0) && Near(pose.position_m.y, 0.5));
    CHECK(Near(pose.orientation_xyzw.w, 1.0));
}

void TestYawAndTranslation()
{
    // +90 degrees about Y (up), then translate by (0, 0, 2).
    uts::Calibration cal;
    CHECK(uts::Calibration::Parse("CALIBRATION 1 0 0 2 0 0.70710678118654752 0 0.70710678118654752", cal));
    auto pose = MakePose();
    cal.Apply(pose);
    // Rotating (1,0.5,0) by +90 deg about Y gives (0,0.5,-1); plus translation.
    CHECK(Near(pose.position_m.x, 0.0));
    CHECK(Near(pose.position_m.y, 0.5));
    CHECK(Near(pose.position_m.z, 1.0));
    CHECK(Near(pose.linear_accel_m_s2.z, -1.0));
    // Identity tracker orientation becomes the calibration rotation.
    CHECK(Near(pose.orientation_xyzw.y, 0.70710678118654752));
    CHECK(Near(pose.orientation_xyzw.w, 0.70710678118654752));
}

void TestNormalisesAndRejects()
{
    uts::Calibration cal;
    CHECK(uts::Calibration::Parse("CALIBRATION 1 0 0 0 0 0 0 2", cal));
    CHECK(Near(cal.rotation.w, 1.0));

    uts::Calibration before = cal;
    CHECK(!uts::Calibration::Parse("CALIBRATION 1 0 0 0 0 0 0 0", cal));
    CHECK(!uts::Calibration::Parse("CALIBRATION 2 0 0 0 0 0 0 1", cal));
    CHECK(!uts::Calibration::Parse("CALIBRATION 1 0 0 0 0 0 1", cal));
    CHECK(!uts::Calibration::Parse("CALIBRATION 1 0 0 0 0 0 0 1 extra", cal));
    CHECK(!uts::Calibration::Parse("CALIBRATION 1 nan 0 0 0 0 0 1", cal));
    CHECK(!uts::Calibration::Parse("POSE 1 0 0 0 0 0 0 1", cal));
    CHECK(Near(cal.rotation.w, before.rotation.w));
}

void WriteFile(const std::string &path, const std::string &content)
{
    std::ofstream out(path, std::ios::trunc);
    out << content;
}

void TestFileReload()
{
    char dir[] = "/tmp/uts-cal-XXXXXX";
    CHECK(::mkdtemp(dir) != nullptr);
    const std::string path = std::string(dir) + "/calibration.txt";

    uts::CalibrationFile file(path);
    CHECK(!file.Refresh()); // missing: identity
    CHECK(Near(file.current().translation_m.x, 0.0));

    WriteFile(path, "# comment\nCALIBRATION 1 1 2 3 0 0 0 1\n");
    CHECK(file.Refresh());
    CHECK(Near(file.current().translation_m.y, 2.0));
    CHECK(!file.Refresh()); // unchanged

    std::this_thread::sleep_for(std::chrono::milliseconds(20));
    WriteFile(path, "garbage\n");
    CHECK(!file.Refresh());
    CHECK(Near(file.current().translation_m.y, 2.0)); // last good value kept

    std::this_thread::sleep_for(std::chrono::milliseconds(20));
    WriteFile(path, "CALIBRATION 1 9 0 0 0 0 0 1\n");
    CHECK(file.Refresh());
    CHECK(Near(file.current().translation_m.x, 9.0));

    ::unlink(path.c_str());
    ::rmdir(dir);
}

} // namespace

int main()
{
    TestIdentity();
    TestYawAndTranslation();
    TestNormalisesAndRejects();
    TestFileReload();
    if (g_failures != 0)
    {
        std::fprintf(stderr, "%d check(s) failed\n", g_failures);
        return 1;
    }
    std::puts("ok");
    return 0;
}
