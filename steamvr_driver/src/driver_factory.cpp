#include "device_provider.hpp"

#include <cstdlib>
#include <cstring>
#include <memory>

#include <openvr_driver.h>

namespace
{

std::unique_ptr<uts::DeviceProvider> g_provider;

const char *ResolveSocketPath()
{
    const char *value = std::getenv("ULTIMATE_TRACKER_SOCKET_PATH");
    if (value != nullptr && value[0] != '\0')
    {
        return value;
    }

    return "/tmp/ultimate-tracker-linux.sock";
}

} // namespace

extern "C" void *HmdDriverFactory(const char *interface_name, int *return_code)
{
    if (std::strcmp(interface_name, vr::IServerTrackedDeviceProvider_Version) == 0)
    {
        if (!g_provider)
        {
            g_provider = std::make_unique<uts::DeviceProvider>(ResolveSocketPath());
        }
        return g_provider.get();
    }

    if (return_code != nullptr)
    {
        *return_code = vr::VRInitError_Init_InterfaceNotFound;
    }

    return nullptr;
}

