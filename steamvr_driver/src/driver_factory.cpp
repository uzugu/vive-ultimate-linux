#include "device_provider.hpp"
#include "ipc_pose_client.hpp"

#include <cstdlib>
#include <cstring>
#include <memory>
#include <string>

#include <openvr_driver.h>

namespace
{

std::unique_ptr<uts::DeviceProvider> g_provider;

std::string ResolveSocketPath()
{
    return uts::DefaultEndpointSpec();
}

} // namespace

#ifdef _WIN32
#define UTS_EXPORT extern "C" __declspec(dllexport)
#else
#define UTS_EXPORT extern "C" __attribute__((visibility("default")))
#endif

UTS_EXPORT void *HmdDriverFactory(const char *interface_name, int *return_code)
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

