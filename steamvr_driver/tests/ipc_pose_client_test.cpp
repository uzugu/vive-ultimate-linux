// OpenVR-free tests for the pose line parser and the Unix socket client.
#include "ipc_pose_client.hpp"

#include <chrono>
#include <cmath>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>
#include <thread>
#include <vector>

#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

namespace
{

int g_failures = 0;

#define CHECK(cond)                                                                                  \
    do                                                                                               \
    {                                                                                                \
        if (!(cond))                                                                                 \
        {                                                                                            \
            std::fprintf(stderr, "%s:%d: CHECK failed: %s\n", __FILE__, __LINE__, #cond);           \
            ++g_failures;                                                                            \
        }                                                                                            \
    } while (0)

std::vector<std::string> ReadFixture(const std::string &name)
{
    std::ifstream in(std::string(UTS_FIXTURE_DIR) + "/" + name);
    CHECK(in.good());
    std::vector<std::string> lines;
    std::string line;
    while (std::getline(in, line))
    {
        if (!line.empty() && line[0] != '#')
        {
            lines.push_back(line);
        }
    }
    return lines;
}

void TestFixtures()
{
    const auto valid = ReadFixture("valid.txt");
    const auto invalid = ReadFixture("invalid.txt");
    CHECK(!valid.empty());
    CHECK(!invalid.empty());
    for (const auto &line : valid)
    {
        uts::TrackedPose pose;
        if (!uts::IpcPoseClient::ParsePoseLine(line, pose))
        {
            std::fprintf(stderr, "should parse: %s\n", line.c_str());
            ++g_failures;
        }
    }
    for (const auto &line : invalid)
    {
        uts::TrackedPose pose;
        if (uts::IpcPoseClient::ParsePoseLine(line, pose))
        {
            std::fprintf(stderr, "should be rejected: %s\n", line.c_str());
            ++g_failures;
        }
    }
}

void TestFieldValues()
{
    uts::TrackedPose pose;
    CHECK(uts::IpcPoseClient::ParsePoseLine(
        "POSE 2 3 AA:BB lost -1.5 0 0.25 0.1 0.2 0.3 0.9 0.5 -9.81 0 99 3 LOST", pose));
    CHECK(pose.tracker_index == 3);
    CHECK(pose.serial == "AA:BB");
    CHECK(pose.status == "lost");
    CHECK(std::fabs(pose.position_m.x + 1.5) < 1e-9);
    CHECK(std::fabs(pose.position_m.z - 0.25) < 1e-9);
    CHECK(std::fabs(pose.orientation_xyzw.x - 0.1) < 1e-9);
    CHECK(std::fabs(pose.orientation_xyzw.w - 0.9) < 1e-9);
    CHECK(std::fabs(pose.linear_accel_m_s2.y + 9.81) < 1e-9);
    CHECK(pose.timestamp_ns == 99);
    CHECK(pose.tracking_code == 3);
    CHECK(pose.tracking_label == "LOST");
}

// Listening socket in a temp dir; the test plays the daemon.
struct FakeDaemon
{
    std::string path;
    int listen_fd = -1;

    FakeDaemon()
    {
        char dir[] = "/tmp/uts-test-XXXXXX";
        CHECK(::mkdtemp(dir) != nullptr);
        path = std::string(dir) + "/pose.sock";
        listen_fd = ::socket(AF_UNIX, SOCK_STREAM, 0);
        sockaddr_un addr {};
        addr.sun_family = AF_UNIX;
        std::snprintf(addr.sun_path, sizeof(addr.sun_path), "%s", path.c_str());
        CHECK(::bind(listen_fd, reinterpret_cast<sockaddr *>(&addr), sizeof(addr)) == 0);
        CHECK(::listen(listen_fd, 1) == 0);
    }

    ~FakeDaemon()
    {
        ::close(listen_fd);
        ::unlink(path.c_str());
        ::rmdir(path.substr(0, path.rfind('/')).c_str());
    }
};

void WriteAll(int fd, const std::string &data)
{
    CHECK(::write(fd, data.data(), data.size()) == static_cast<ssize_t>(data.size()));
}

void PollUntil(uts::IpcPoseClient &client, std::vector<uts::TrackedPose> &seen, std::size_t want)
{
    for (int i = 0; i < 200 && seen.size() < want && client.IsConnected(); ++i)
    {
        client.Poll([&](const uts::TrackedPose &p) { seen.push_back(p); });
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
    }
}

void TestSocketStreaming()
{
    FakeDaemon daemon;
    uts::IpcPoseClient client(daemon.path);
    CHECK(client.Connect());
    const int conn = ::accept(daemon.listen_fd, nullptr, nullptr);
    CHECK(conn >= 0);

    // One line split across two writes, a garbage line, then a full line.
    const std::string a = "POSE 1 0 t0 ok 1 2 3 0 0 0 1 0 0 0 10\n";
    WriteAll(conn, a.substr(0, 15));
    std::vector<uts::TrackedPose> seen;
    client.Poll([&](const uts::TrackedPose &p) { seen.push_back(p); });
    CHECK(seen.empty());
    WriteAll(conn, a.substr(15) + "garbage line\nPOSE 1 1 t1 ok 4 5 6 0 0 0 1 0 0 0 20\n");
    PollUntil(client, seen, 2);
    CHECK(seen.size() == 2);
    if (seen.size() == 2)
    {
        CHECK(seen[0].serial == "t0");
        CHECK(seen[1].serial == "t1");
        CHECK(seen[1].timestamp_ns == 20);
    }

    // Daemon goes away: client must report disconnected so the provider can mark trackers lost.
    ::close(conn);
    for (int i = 0; i < 200 && client.IsConnected(); ++i)
    {
        client.Poll([](const uts::TrackedPose &) {});
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
    }
    CHECK(!client.IsConnected());
}

void TestMissingDaemon()
{
    uts::IpcPoseClient client("/tmp/uts-does-not-exist.sock");
    CHECK(!client.Connect());
    CHECK(!client.IsConnected());
    client.Poll([](const uts::TrackedPose &) { CHECK(false); });
}

void TestNewlineFlood()
{
    FakeDaemon daemon;
    uts::IpcPoseClient client(daemon.path);
    CHECK(client.Connect());
    const int conn = ::accept(daemon.listen_fd, nullptr, nullptr);
    std::thread writer([&] {
        const std::string chunk(65536, 'x');
        for (int i = 0; i < 40; ++i)
        {
            if (::write(conn, chunk.data(), chunk.size()) < 0)
            {
                break;
            }
        }
    });
    for (int i = 0; i < 400 && client.IsConnected(); ++i)
    {
        client.Poll([](const uts::TrackedPose &) {});
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
    }
    CHECK(!client.IsConnected());
    ::close(conn);
    writer.join();
}

// Optional end-to-end check against the real Python daemon (see .github/workflows/ci.yml).
void TestAgainstRealDaemon(const char *socket_path)
{
    uts::IpcPoseClient client(socket_path);
    std::vector<uts::TrackedPose> seen;
    for (int i = 0; i < 400 && seen.size() < 6; ++i)
    {
        client.Poll([&](const uts::TrackedPose &p) { seen.push_back(p); });
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    CHECK(seen.size() >= 6);
    for (const auto &pose : seen)
    {
        CHECK(pose.serial.rfind("mock-", 0) == 0);
        CHECK(pose.status == "ok");
        CHECK(pose.tracking_code == 2);
        CHECK(pose.tracking_label == "OK");
    }
}

} // namespace

int main()
{
    std::signal(SIGPIPE, SIG_IGN);
    TestFixtures();
    TestFieldValues();
    TestSocketStreaming();
    TestMissingDaemon();
    TestNewlineFlood();
    if (const char *socket_path = std::getenv("UTS_E2E_SOCKET"))
    {
        TestAgainstRealDaemon(socket_path);
    }
    if (g_failures != 0)
    {
        std::fprintf(stderr, "%d check(s) failed\n", g_failures);
        return 1;
    }
    std::puts("ok");
    return 0;
}
