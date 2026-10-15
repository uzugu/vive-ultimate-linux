// OpenVR-free tests for the pose line parser and the socket client (Unix socket and loopback TCP).
#include "ipc_pose_client.hpp"

#include <chrono>
#include <cmath>
#include <string>
#include <csignal>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>
#include <thread>
#include <vector>

#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#else
#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#endif

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

void TestStatusFixtures()
{
    for (const auto &line : ReadFixture("status_valid.txt"))
    {
        uts::BatteryStatus battery;
        uts::ButtonState buttons;
        const bool ok = line.rfind("BATTERY", 0) == 0 ? uts::IpcPoseClient::ParseBatteryLine(line, battery)
                                                       : uts::IpcPoseClient::ParseButtonsLine(line, buttons);
        if (!ok)
        {
            std::fprintf(stderr, "should parse: %s\n", line.c_str());
            ++g_failures;
        }
    }
    for (const auto &line : ReadFixture("status_invalid.txt"))
    {
        uts::BatteryStatus battery;
        uts::ButtonState buttons;
        const bool ok = line.rfind("BATTERY", 0) == 0 ? uts::IpcPoseClient::ParseBatteryLine(line, battery)
                                                       : uts::IpcPoseClient::ParseButtonsLine(line, buttons);
        if (ok)
        {
            std::fprintf(stderr, "should be rejected: %s\n", line.c_str());
            ++g_failures;
        }
    }

    uts::BatteryStatus battery;
    CHECK(uts::IpcPoseClient::ParseBatteryLine("BATTERY 1 AA:BB 86 1", battery));
    CHECK(battery.serial == "AA:BB" && battery.percent == 86 && battery.charging);
    uts::ButtonState buttons;
    CHECK(uts::IpcPoseClient::ParseButtonsLine("BUTTONS 1 AA:BB 6", buttons));
    CHECK(buttons.mask == (uts::kButtonGrip | uts::kButtonTrigger));
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

// Minimal portable socket helpers: fds are carried as intptr_t (SOCKET on Windows).
using Fd = std::intptr_t;

void CloseFd(Fd fd)
{
#ifdef _WIN32
    ::closesocket(static_cast<SOCKET>(fd));
#else
    ::close(static_cast<int>(fd));
#endif
}

Fd AcceptFd(Fd listen_fd)
{
#ifdef _WIN32
    return static_cast<Fd>(::accept(static_cast<SOCKET>(listen_fd), nullptr, nullptr));
#else
    return ::accept(static_cast<int>(listen_fd), nullptr, nullptr);
#endif
}

long ReadFd(Fd fd, char *buffer, std::size_t size)
{
#ifdef _WIN32
    return ::recv(static_cast<SOCKET>(fd), buffer, static_cast<int>(size), 0);
#else
    return static_cast<long>(::recv(static_cast<int>(fd), buffer, size, 0));
#endif
}

long SendFd(Fd fd, const char *data, std::size_t size)
{
#ifdef _WIN32
    return ::send(static_cast<SOCKET>(fd), data, static_cast<int>(size), 0);
#else
    return static_cast<long>(::send(static_cast<int>(fd), data, size, MSG_NOSIGNAL));
#endif
}

// Listening socket; the test plays the daemon. Loopback TCP on an ephemeral port everywhere, and
// additionally a Unix socket in a temp dir where the platform has them.
struct FakeDaemon
{
    enum class Kind
    {
        Tcp,
        Unix
    };

    std::string path; // endpoint spec handed to IpcPoseClient
    Fd listen_fd = -1;
    std::string unix_path;

    explicit FakeDaemon(Kind kind = Kind::Tcp)
    {
#ifdef _WIN32
        static const bool started = [] {
            WSADATA data;
            return ::WSAStartup(MAKEWORD(2, 2), &data) == 0;
        }();
        CHECK(started);
#endif
        if (kind == Kind::Tcp)
        {
            listen_fd = static_cast<Fd>(::socket(AF_INET, SOCK_STREAM, 0));
            sockaddr_in addr {};
            addr.sin_family = AF_INET;
            addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
            addr.sin_port = 0;
            CHECK(::bind(static_cast<decltype(::socket(0, 0, 0))>(listen_fd), reinterpret_cast<sockaddr *>(&addr),
                         sizeof(addr)) == 0);
            socklen_t len = sizeof(addr);
            CHECK(::getsockname(static_cast<decltype(::socket(0, 0, 0))>(listen_fd), reinterpret_cast<sockaddr *>(&addr),
                                &len) == 0);
            CHECK(::listen(static_cast<decltype(::socket(0, 0, 0))>(listen_fd), 1) == 0);
            path = "tcp:127.0.0.1:" + std::to_string(ntohs(addr.sin_port));
            return;
        }
#ifndef _WIN32
        char dir[] = "/tmp/uts-test-XXXXXX";
        CHECK(::mkdtemp(dir) != nullptr);
        unix_path = std::string(dir) + "/pose.sock";
        path = unix_path;
        listen_fd = ::socket(AF_UNIX, SOCK_STREAM, 0);
        sockaddr_un addr {};
        addr.sun_family = AF_UNIX;
        std::snprintf(addr.sun_path, sizeof(addr.sun_path), "%s", unix_path.c_str());
        CHECK(::bind(static_cast<int>(listen_fd), reinterpret_cast<sockaddr *>(&addr), sizeof(addr)) == 0);
        CHECK(::listen(static_cast<int>(listen_fd), 1) == 0);
#endif
    }

    ~FakeDaemon()
    {
        CloseFd(listen_fd);
#ifndef _WIN32
        if (!unix_path.empty())
        {
            ::unlink(unix_path.c_str());
            ::rmdir(unix_path.substr(0, unix_path.rfind('/')).c_str());
        }
#endif
    }
};

void WriteAll(Fd fd, const std::string &data)
{
    CHECK(SendFd(fd, data.data(), data.size()) == static_cast<long>(data.size()));
}

void PollUntil(uts::IpcPoseClient &client, std::vector<uts::TrackedPose> &seen, std::size_t want)
{
    for (int i = 0; i < 200 && seen.size() < want && client.IsConnected(); ++i)
    {
        client.Poll([&](const uts::TrackedPose &p) { seen.push_back(p); });
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
    }
}

void TestSocketStreaming(FakeDaemon::Kind kind)
{
    FakeDaemon daemon(kind);
    uts::IpcPoseClient client(daemon.path);
    CHECK(client.Connect());
    const Fd conn = AcceptFd(daemon.listen_fd);
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
    CloseFd(conn);
    for (int i = 0; i < 200 && client.IsConnected(); ++i)
    {
        client.Poll([](const uts::TrackedPose &) {});
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
    }
    CHECK(!client.IsConnected());
}

void TestStatusOverSocket()
{
    FakeDaemon daemon;
    uts::IpcPoseClient client(daemon.path);
    CHECK(client.Connect());
    const Fd conn = AcceptFd(daemon.listen_fd);
    WriteAll(conn,
             "BATTERY 1 t0 50 0\nHELLO 2 future message\nBUTTONS 1 t0 4\nBATTERY 1 t0 999 0\n"
             "POSE 1 0 t0 ok 1 2 3 0 0 0 1 0 0 0 10\n");
    int batteries = 0, buttons = 0, poses = 0;
    uts::IpcPoseClient::Handlers handlers;
    handlers.on_battery = [&](const uts::BatteryStatus &) { ++batteries; };
    handlers.on_buttons = [&](const uts::ButtonState &) { ++buttons; };
    handlers.on_pose = [&](const uts::TrackedPose &) { ++poses; };
    for (int i = 0; i < 100 && poses == 0; ++i)
    {
        client.Poll(handlers);
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
    }
    CHECK(batteries == 1); // the 999% line is dropped, the unknown tag is ignored
    CHECK(buttons == 1);
    CHECK(poses == 1);
    CloseFd(conn);
}

void TestEndpoints()
{
    uts::Endpoint ep;
    CHECK(uts::ParseEndpoint("/tmp/x.sock", ep) && ep.kind == uts::Endpoint::Kind::Unix && ep.path == "/tmp/x.sock");
    CHECK(uts::ParseEndpoint("unix:/tmp/x.sock", ep) && ep.path == "/tmp/x.sock");
    CHECK(uts::ParseEndpoint("tcp:127.0.0.1:38450", ep) && ep.kind == uts::Endpoint::Kind::Tcp && ep.host == "127.0.0.1" &&
          ep.port == 38450);
    CHECK(uts::ParseEndpoint("tcp:::1:5000", ep) && ep.host == "::1" && ep.port == 5000);
    for (const char *bad : {"", "unix:", "tcp:127.0.0.1", "tcp:127.0.0.1:0", "tcp:127.0.0.1:99999", "tcp:0.0.0.0:5000",
                            "tcp:example.com:5000", "tcp:10.0.0.5:5000", "tcp::5000"})
    {
        CHECK(!uts::ParseEndpoint(bad, ep));
    }
}

void TestHaptic()
{
    std::string line;
    CHECK(uts::IpcPoseClient::FormatHapticLine({"AA:BB", 0.1, 160.0, 1.0}, line));
    CHECK(line == "HAPTIC 1 AA:BB 0.1000 160.00 1.0000\n");
    CHECK(uts::IpcPoseClient::FormatHapticLine({"t", 99.0, 5000.0, 3.0}, line));
    CHECK(line == "HAPTIC 1 t 10.0000 1000.00 1.0000\n"); // clamped
    CHECK(!uts::IpcPoseClient::FormatHapticLine({"bad serial", 0.1, 1.0, 1.0}, line));
    CHECK(!uts::IpcPoseClient::FormatHapticLine({"", 0.1, 1.0, 1.0}, line));
    CHECK(!uts::IpcPoseClient::FormatHapticLine({"t", std::nan(""), 1.0, 1.0}, line));

    FakeDaemon daemon;
    uts::IpcPoseClient client(daemon.path);
    CHECK(!client.SendHaptic({"t", 0.1, 1.0, 1.0})); // not connected yet
    CHECK(client.Connect());
    const Fd conn = AcceptFd(daemon.listen_fd);
    CHECK(client.SendHaptic({"t0", 0.5, 100.0, 0.5}));
    char buffer[128] = {};
    const long n = ReadFd(conn, buffer, sizeof(buffer) - 1);
    CHECK(n > 0 && std::string(buffer, static_cast<std::size_t>(n)) == "HAPTIC 1 t0 0.5000 100.00 0.5000\n");
    CloseFd(conn);
}

void TestMissingDaemon()
{
    uts::IpcPoseClient client("tcp:127.0.0.1:1"); // nothing listens on port 1
    CHECK(!client.Connect());
    CHECK(!client.IsConnected());
    client.Poll([](const uts::TrackedPose &) { CHECK(false); });
    uts::IpcPoseClient invalid("tcp:8.8.8.8:80"); // non-loopback endpoints are refused outright
    CHECK(!invalid.Connect());
}

void TestNewlineFlood()
{
    FakeDaemon daemon;
    uts::IpcPoseClient client(daemon.path);
    CHECK(client.Connect());
    const Fd conn = AcceptFd(daemon.listen_fd);
    std::thread writer([&] {
        const std::string chunk(65536, 'x');
        for (int i = 0; i < 40; ++i)
        {
            if (SendFd(conn, chunk.data(), chunk.size()) < 0)
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
    CloseFd(conn);
    writer.join();
}

// Optional end-to-end check against the real Python daemon (see .github/workflows/ci.yml).
void TestAgainstRealDaemon(const char *socket_path)
{
    uts::IpcPoseClient client(socket_path);
    std::vector<uts::TrackedPose> seen;
    int batteries = 0, buttons = 0;
    uts::IpcPoseClient::Handlers handlers;
    handlers.on_pose = [&](const uts::TrackedPose &p) { seen.push_back(p); };
    handlers.on_battery = [&](const uts::BatteryStatus &b) { batteries += b.serial.rfind("mock-", 0) == 0; };
    handlers.on_buttons = [&](const uts::ButtonState &b) { buttons += b.serial.rfind("mock-", 0) == 0; };
    for (int i = 0; i < 400 && (seen.size() < 6 || batteries == 0 || buttons == 0); ++i)
    {
        client.Poll(handlers);
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    CHECK(seen.size() >= 6);
    CHECK(batteries > 0);
    CHECK(buttons > 0);
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
#ifndef _WIN32
    std::signal(SIGPIPE, SIG_IGN);
#endif
    TestEndpoints();
    TestFixtures();
    TestFieldValues();
    TestStatusFixtures();
    TestStatusOverSocket();
    TestSocketStreaming(FakeDaemon::Kind::Tcp);
#ifndef _WIN32
    TestSocketStreaming(FakeDaemon::Kind::Unix);
#endif
    TestHaptic();
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
