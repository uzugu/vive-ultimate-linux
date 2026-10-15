#pragma once

#include "calibration.hpp"
#include "ipc_pose_client.hpp"
#include "ultimate_tracker_device.hpp"

#include <memory>
#include <string>
#include <unordered_map>

#include <openvr_driver.h>

namespace uts
{

class DeviceProvider final : public vr::IServerTrackedDeviceProvider
{
  public:
    explicit DeviceProvider(std::string socket_path);

    vr::EVRInitError Init(vr::IVRDriverContext *driver_context) override;
    void Cleanup() override;
    const char *const *GetInterfaceVersions() override;
    void RunFrame() override;
    bool ShouldBlockStandbyMode() override;
    void EnterStandby() override;
    void LeaveStandby() override;

  private:
    UltimateTrackerDevice *EnsureDeviceForSerial(const std::string &serial);
    void ReloadSettings();
    void MarkAllDisconnected();

    std::string socket_path_;
    bool reload_settings_once_ = true;
    IpcPoseClient pose_client_;
    CalibrationFile calibration_;
    std::unordered_map<std::string, std::unique_ptr<UltimateTrackerDevice>> devices_;
};

} // namespace uts
