#include "ultimate_tracker_device.hpp"

#include "driver_log.hpp"

#include <algorithm>
#include <cmath>
#include <cstring>

namespace uts
{

UltimateTrackerDevice::UltimateTrackerDevice(std::string serial) : serial_(std::move(serial)) {}

vr::EVRInitError UltimateTrackerDevice::Activate(std::uint32_t object_id)
{
    object_id_ = object_id;
    property_container_ = vr::VRProperties()->TrackedDeviceToPropertyContainer(object_id_);

    vr::VRProperties()->SetStringProperty(property_container_, vr::Prop_TrackingSystemName_String, "ultimate_tracker_linux");
    vr::VRProperties()->SetStringProperty(property_container_, vr::Prop_ModelNumber_String, "VIVE Ultimate Tracker");
    vr::VRProperties()->SetStringProperty(property_container_, vr::Prop_SerialNumber_String, serial_.c_str());
    vr::VRProperties()->SetBoolProperty(property_container_, vr::Prop_DeviceProvidesBatteryStatus_Bool, true);
    vr::VRProperties()->SetStringProperty(
        property_container_, vr::Prop_InputProfilePath_String, "{ultimate_tracker_linux}/input/ultimate_tracker_profile.json");

    // Same button set HTC's driver exposes; the daemon sends a bitmask (see protocol/pose-v1.md).
    static const char *const kButtonPaths[kButtonCount] = {
        "/input/power/click", "/input/grip/click", "/input/trigger/click", "/input/thumb/click",
        "/input/application_menu/click"};
    for (int i = 0; i < kButtonCount; ++i)
    {
        vr::VRDriverInput()->CreateBooleanComponent(property_container_, kButtonPaths[i], &button_handles_[i]);
    }
    PublishBattery();
    PublishButtons();

    Logf("activated tracker %s as object_id=%u", serial_.c_str(), object_id_);
    return vr::VRInitError_None;
}

void UltimateTrackerDevice::Deactivate()
{
    Logf("deactivated tracker %s", serial_.c_str());
    object_id_ = vr::k_unTrackedDeviceIndexInvalid;
    property_container_ = vr::k_ulInvalidPropertyContainer;
    for (auto &handle : button_handles_)
    {
        handle = vr::k_ulInvalidInputComponentHandle;
    }
}

void UltimateTrackerDevice::EnterStandby() {}

void *UltimateTrackerDevice::GetComponent(const char *component_name_and_version)
{
    (void)component_name_and_version;
    return nullptr;
}

void UltimateTrackerDevice::DebugRequest(const char *request, char *response_buffer, std::uint32_t response_buffer_size)
{
    (void)request;
    if (response_buffer != nullptr && response_buffer_size > 0)
    {
        response_buffer[0] = '\0';
    }
}

vr::DriverPose_t UltimateTrackerDevice::GetPose()
{
    std::scoped_lock lock(pose_mutex_);
    return current_pose_;
}

const std::string &UltimateTrackerDevice::serial() const
{
    return serial_;
}

void UltimateTrackerDevice::UpdateFromPose(const TrackedPose &pose)
{
    vr::DriverPose_t driver_pose = MakeDefaultPose();
    const bool pose_usable = IsPoseUsable(pose);
    driver_pose.deviceIsConnected = true;
    driver_pose.poseIsValid = pose_usable;
    driver_pose.result = driver_pose.poseIsValid ? vr::TrackingResult_Running_OK : vr::TrackingResult_Running_OutOfRange;
    driver_pose.vecPosition[0] = pose.position_m.x;
    driver_pose.vecPosition[1] = pose.position_m.y;
    driver_pose.vecPosition[2] = pose.position_m.z;
    driver_pose.qRotation = ToOpenVrQuaternion(pose.orientation_xyzw);
    driver_pose.poseTimeOffset = 0.0;

    {
        std::scoped_lock lock(pose_mutex_);
        current_pose_ = driver_pose;
    }

    if (object_id_ != vr::k_unTrackedDeviceIndexInvalid)
    {
        vr::VRServerDriverHost()->TrackedDevicePoseUpdated(object_id_, driver_pose, sizeof(vr::DriverPose_t));
    }
}

bool UltimateTrackerDevice::IsPoseUsable(const TrackedPose &pose)
{
    if (pose.status == "ok")
    {
        return true;
    }

    if (pose.tracking_code == 2 || pose.tracking_code == 18)
    {
        return true;
    }

    if (pose.tracking_code == 3 || pose.tracking_code == 4 || pose.status == "lost")
    {
        return false;
    }

    constexpr double epsilon = 0.0001;
    const bool has_nonzero_position = std::abs(pose.position_m.x) > epsilon || std::abs(pose.position_m.y) > epsilon ||
                                      std::abs(pose.position_m.z) > epsilon;
    return has_nonzero_position;
}

void UltimateTrackerDevice::UpdateBattery(const BatteryStatus &battery)
{
    battery_ = battery;
    have_battery_ = true;
    PublishBattery();
}

void UltimateTrackerDevice::UpdateButtons(const ButtonState &buttons)
{
    button_mask_ = buttons.mask;
    PublishButtons();
}

void UltimateTrackerDevice::PublishBattery()
{
    if (property_container_ == vr::k_ulInvalidPropertyContainer || !have_battery_)
    {
        return;
    }
    vr::VRProperties()->SetFloatProperty(
        property_container_, vr::Prop_DeviceBatteryPercentage_Float, static_cast<float>(battery_.percent) / 100.0f);
    vr::VRProperties()->SetBoolProperty(property_container_, vr::Prop_DeviceIsCharging_Bool, battery_.charging);
}

void UltimateTrackerDevice::PublishButtons()
{
    if (property_container_ == vr::k_ulInvalidPropertyContainer)
    {
        return;
    }
    for (int i = 0; i < kButtonCount; ++i)
    {
        vr::VRDriverInput()->UpdateBooleanComponent(button_handles_[i], (button_mask_ & (1 << i)) != 0, 0.0);
    }
}

void UltimateTrackerDevice::MarkDisconnected()
{
    vr::DriverPose_t driver_pose = MakeDefaultPose();
    driver_pose.deviceIsConnected = false;
    driver_pose.poseIsValid = false;
    driver_pose.result = vr::TrackingResult_Running_OutOfRange;

    {
        std::scoped_lock lock(pose_mutex_);
        current_pose_ = driver_pose;
    }

    if (object_id_ != vr::k_unTrackedDeviceIndexInvalid)
    {
        vr::VRServerDriverHost()->TrackedDevicePoseUpdated(object_id_, driver_pose, sizeof(vr::DriverPose_t));
    }
}

vr::DriverPose_t UltimateTrackerDevice::MakeDefaultPose()
{
    vr::DriverPose_t pose {};
    pose.qWorldFromDriverRotation.w = 1.0;
    pose.qDriverFromHeadRotation.w = 1.0;
    pose.qRotation.w = 1.0;
    pose.deviceIsConnected = false;
    pose.poseIsValid = false;
    pose.result = vr::TrackingResult_Uninitialized;
    return pose;
}

vr::HmdQuaternion_t UltimateTrackerDevice::ToOpenVrQuaternion(const Quat &quat)
{
    vr::HmdQuaternion_t out {};
    out.w = quat.w;
    out.x = quat.x;
    out.y = quat.y;
    out.z = quat.z;
    return out;
}

} // namespace uts
