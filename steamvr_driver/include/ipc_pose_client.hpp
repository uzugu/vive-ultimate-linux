#pragma once

#include "pose_types.hpp"

#include <functional>
#include <string>

namespace uts
{

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

    void Poll(const std::function<void(const TrackedPose &)> &on_pose);

    // Parses one `POSE 1|2 ...` line (see protocol/pose-v1.md). Returns false on any malformed
    // or non-finite input, leaving `out_pose` unspecified.
    static bool ParsePoseLine(const std::string &line, TrackedPose &out_pose);

  private:

    std::string socket_path_;
    int socket_fd_ = -1;
    std::string read_buffer_;
};

} // namespace uts
