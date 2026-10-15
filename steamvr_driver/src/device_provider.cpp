#include "device_provider.hpp"

#include "driver_log.hpp"

#include <utility>

namespace uts
{

DeviceProvider::DeviceProvider(std::string socket_path)
    : socket_path_(std::move(socket_path)), pose_client_(socket_path_), calibration_(DefaultCalibrationPath())
{
}

vr::EVRInitError DeviceProvider::Init(vr::IVRDriverContext *driver_context)
{
    VR_INIT_SERVER_DRIVER_CONTEXT(driver_context);
    ReloadSettings();
    Logf("device provider initialized using socket %s, calibration file %s", pose_client_.SocketPath().c_str(),
         calibration_.path().c_str());
    return vr::VRInitError_None;
}

void DeviceProvider::Cleanup()
{
    devices_.clear();
    pose_client_.Disconnect();
    VR_CLEANUP_SERVER_DRIVER_CONTEXT();
}

const char *const *DeviceProvider::GetInterfaceVersions()
{
    return vr::k_InterfaceVersions;
}

void DeviceProvider::RunFrame()
{
    if (reload_settings_once_)
    {
        reload_settings_once_ = false;
        ReloadSettings();
    }

    calibration_.Refresh();

    const bool was_connected = pose_client_.IsConnected();
    IpcPoseClient::Handlers handlers;
    handlers.on_pose = [this](const TrackedPose &raw_pose) {
        TrackedPose pose = raw_pose;
        // Judge usability on the raw pose: a calibration offset must not make an all-zero pose look live.
        if (UltimateTrackerDevice::IsPoseUsable(pose))
        {
            calibration_.current().Apply(pose);
        }
        auto *device = EnsureDeviceForSerial(pose.serial);
        if (device != nullptr)
        {
            device->UpdateFromPose(pose);
        }
    };
    handlers.on_battery = [this](const BatteryStatus &battery) {
        if (auto *device = EnsureDeviceForSerial(battery.serial))
        {
            device->UpdateBattery(battery);
        }
    };
    handlers.on_buttons = [this](const ButtonState &buttons) {
        if (auto *device = EnsureDeviceForSerial(buttons.serial))
        {
            device->UpdateButtons(buttons);
        }
    };
    pose_client_.Poll(handlers);

    if (was_connected && !pose_client_.IsConnected())
    {
        MarkAllDisconnected();
    }
}

bool DeviceProvider::ShouldBlockStandbyMode()
{
    return false;
}

void DeviceProvider::EnterStandby() {}

void DeviceProvider::LeaveStandby() {}

void DeviceProvider::ReloadSettings()
{
    vr::EVRSettingsError error = vr::VRSettingsError_None;
    char socket_path[1024] = {};
    vr::VRSettings()->GetString(
        "driver_ultimate_tracker_linux",
        "socket_path",
        socket_path,
        sizeof(socket_path),
        &error);

    if (error == vr::VRSettingsError_None && socket_path[0] != '\0')
    {
        socket_path_ = socket_path;
        pose_client_.SetSocketPath(socket_path_);
    }

    Logf("settings resolved socket path to %s", pose_client_.SocketPath().c_str());
}

UltimateTrackerDevice *DeviceProvider::EnsureDeviceForSerial(const std::string &serial)
{
    const auto it = devices_.find(serial);
    if (it != devices_.end())
    {
        return it->second.get();
    }

    auto device = std::make_unique<UltimateTrackerDevice>(serial);
    auto *device_ptr = device.get();
    const bool added =
        vr::VRServerDriverHost()->TrackedDeviceAdded(serial.c_str(), vr::TrackedDeviceClass_GenericTracker, device_ptr);

    if (!added)
    {
        Logf("SteamVR rejected tracker device %s", serial.c_str());
        return nullptr;
    }

    Logf("registered tracker device %s", serial.c_str());
    devices_.emplace(serial, std::move(device));
    return device_ptr;
}

void DeviceProvider::MarkAllDisconnected()
{
    for (auto &[serial, device] : devices_)
    {
        (void)serial;
        device->MarkDisconnected();
    }
}

} // namespace uts
