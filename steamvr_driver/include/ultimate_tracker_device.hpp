#pragma once

#include "pose_types.hpp"

#include <mutex>
#include <string>

#include <openvr_driver.h>

namespace uts
{

class UltimateTrackerDevice final : public vr::ITrackedDeviceServerDriver
{
  public:
    explicit UltimateTrackerDevice(std::string serial);

    vr::EVRInitError Activate(std::uint32_t object_id) override;
    void Deactivate() override;
    void EnterStandby() override;
    void *GetComponent(const char *component_name_and_version) override;
    void DebugRequest(const char *request, char *response_buffer, std::uint32_t response_buffer_size) override;
    vr::DriverPose_t GetPose() override;

    const std::string &serial() const;
    void UpdateFromPose(const TrackedPose &pose);
    void MarkDisconnected();
    static bool IsPoseUsable(const TrackedPose &pose);

  private:
    static vr::DriverPose_t MakeDefaultPose();
    static vr::HmdQuaternion_t ToOpenVrQuaternion(const Quat &quat);

    std::string serial_;
    std::uint32_t object_id_ = vr::k_unTrackedDeviceIndexInvalid;
    vr::PropertyContainerHandle_t property_container_ = vr::k_ulInvalidPropertyContainer;
    mutable std::mutex pose_mutex_;
    vr::DriverPose_t current_pose_ = MakeDefaultPose();
};

} // namespace uts
