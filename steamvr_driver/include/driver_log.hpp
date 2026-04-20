#pragma once

#include <cstdarg>
#include <cstdio>

namespace uts
{

inline void Logf(const char *fmt, ...)
{
    std::va_list args;
    va_start(args, fmt);
    std::fputs("[ultimate_tracker_linux] ", stderr);
    std::vfprintf(stderr, fmt, args);
    std::fputc('\n', stderr);
    va_end(args);
}

} // namespace uts

