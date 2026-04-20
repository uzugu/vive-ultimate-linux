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

  private:
    bool ParseLine(const std::string &line, TrackedPose &out_pose) const;

    std::string socket_path_;
    int socket_fd_ = -1;
    std::string read_buffer_;
};

} // namespace uts
