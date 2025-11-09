#include <pybind11/pybind11.h>
#include <iostream>
#include <pybind11/stl.h>
#include <vector>
#include <string>
#include <fstream>
#include <stdexcept>
#include <optional>
#include <tuple>
#include <cerrno>

#include "../native_log_bridge.h"

#define CALENDAR_CORE_COMPONENT "backend.native.calendar.core"
#define CALENDAR_MODULE_COMPONENT "backend.native.calendar.module"

#define CALENDAR_LOG(level, message, details) \
    native_log_bridge_log(level, CALENDAR_CORE_COMPONENT, __FUNCTION__, __LINE__, message, details)

#define CALENDAR_LOG_INFO(message, details) \
    CALENDAR_LOG(NATIVE_LOG_LEVEL_INFO, message, details)

#define CALENDAR_LOG_WARNING(message, details) \
    CALENDAR_LOG(NATIVE_LOG_LEVEL_WARNING, message, details)

#define CALENDAR_LOG_ERROR(message, details) \
    CALENDAR_LOG(NATIVE_LOG_LEVEL_ERROR, message, details)

#ifdef _WIN32
#include <windows.h>
#else
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#endif

namespace py = pybind11;

class NativeCalendar {
private:
    int start_year_;
    const unsigned char* bitmap_ = nullptr;
    size_t bitmap_size_ = 0;
    std::vector<int> year_offsets_;

#ifdef _WIN32
    HANDLE hFile_ = NULL;
    HANDLE hMapFile_ = NULL;
#else
    int fd_ = -1;
#endif

    void unmap_file() {
#ifdef _WIN32
        if (bitmap_) {
            UnmapViewOfFile(bitmap_);
            bitmap_ = nullptr;
        }
        if (hMapFile_) {
            CloseHandle(hMapFile_);
            hMapFile_ = NULL;
        }
        if (hFile_) {
            CloseHandle(hFile_);
            hFile_ = NULL;
        }
#else
        if (bitmap_ && bitmap_size_ > 0) {
            munmap((void*)bitmap_, bitmap_size_);
            bitmap_ = nullptr;
        }
        if (fd_ != -1) {
            close(fd_);
            fd_ = -1;
        }
#endif
    }


public:
    NativeCalendar(int start_year, const std::string& bitmap_path) : start_year_(start_year) {
#ifdef _WIN32
        hFile_ = CreateFileA(bitmap_path.c_str(), GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
        if (hFile_ == INVALID_HANDLE_VALUE) {
            CALENDAR_LOG_ERROR("Failed to open calendar bitmap file", bitmap_path.c_str());
            throw std::runtime_error("Failed to open file for mapping.");
        }

        DWORD fileSize = GetFileSize(hFile_, NULL);
        if (fileSize < 8) {
            CloseHandle(hFile_);
            std::string details = "path=" + bitmap_path + ", size=" + std::to_string(fileSize);
            CALENDAR_LOG_ERROR("Invalid calendar file size", details.c_str());
            throw std::runtime_error("Invalid calendar file: too small");
        }

        hMapFile_ = CreateFileMapping(hFile_, NULL, PAGE_READONLY, 0, 0, "Local\\TradingCalendarSharedMemory");
        if (hMapFile_ == NULL) {
            CloseHandle(hFile_);
            std::string details = "path=" + bitmap_path + ", error_code=" + std::to_string(GetLastError());
            CALENDAR_LOG_ERROR("Failed to create file mapping", details.c_str());
            throw std::runtime_error("Failed to create file mapping.");
        }

        const unsigned char* mapped_data = (const unsigned char*)MapViewOfFile(hMapFile_, FILE_MAP_READ, 0, 0, 0);
        if (mapped_data == NULL) {
            CloseHandle(hMapFile_);
            CloseHandle(hFile_);
            std::string details = "path=" + bitmap_path + ", error_code=" + std::to_string(GetLastError());
            CALENDAR_LOG_ERROR("Failed to map calendar file view", details.c_str());
            throw std::runtime_error("Failed to map view of file.");
        }
        // Skip 8-byte ASCII header YYYYMMDD, then bitmap data
        bitmap_ = mapped_data + 8;
        bitmap_size_ = static_cast<size_t>(fileSize - 8) * 8; // number of bits
#else
        fd_ = open(bitmap_path.c_str(), O_RDONLY);
        if (fd_ == -1) {
            CALENDAR_LOG_ERROR("Failed to open calendar bitmap file", bitmap_path.c_str());
            throw std::runtime_error("Failed to open file for mapping.");
        }

        struct stat sb;
        if (fstat(fd_, &sb) == -1) {
            close(fd_);
            std::string details = "path=" + bitmap_path + ", errno=" + std::to_string(errno);
            CALENDAR_LOG_ERROR("Failed to stat calendar file", details.c_str());
            throw std::runtime_error("Failed to get file size.");
        }
        if (sb.st_size < 8) {
            close(fd_);
            std::string details = "path=" + bitmap_path + ", size=" + std::to_string(sb.st_size);
            CALENDAR_LOG_ERROR("Invalid calendar file size", details.c_str());
            throw std::runtime_error("Invalid calendar file: too small");
        }

        const char* mapped_data = (const char*)mmap(NULL, sb.st_size, PROT_READ, MAP_SHARED, fd_, 0);
        if (mapped_data == MAP_FAILED) {
            close(fd_);
            std::string details = "path=" + bitmap_path + ", errno=" + std::to_string(errno);
            CALENDAR_LOG_ERROR("Failed to map calendar file", details.c_str());
            throw std::runtime_error("Failed to map file.");
        }
        // Skip 8-byte ASCII header YYYYMMDD, then bitmap data
        bitmap_ = reinterpret_cast<const unsigned char*>(mapped_data + 8);
        bitmap_size_ = static_cast<size_t>(sb.st_size - 8) * 8; // number of bits
#endif

        std::string load_details =
            "start_year=" + std::to_string(start_year) + ", path=" + bitmap_path;
        CALENDAR_LOG_INFO("Calendar bitmap mapped successfully", load_details.c_str());

        year_offsets_.push_back(0);
        for (int year = start_year; year < start_year + 100; ++year) {
            year_offsets_.push_back(year_offsets_.back() + (is_leap(year) ? 366 : 365));
        }
    }

    ~NativeCalendar() {
        unmap_file();
    }
    
    // Prevent copying and assignment
    NativeCalendar(const NativeCalendar&) = delete;
    NativeCalendar& operator=(const NativeCalendar&) = delete;

    // Move constructor
    NativeCalendar(NativeCalendar&& other) noexcept
        : start_year_(other.start_year_), bitmap_(other.bitmap_), bitmap_size_(other.bitmap_size_), year_offsets_(std::move(other.year_offsets_))
#ifdef _WIN32
        , hFile_(other.hFile_), hMapFile_(other.hMapFile_)
#else
        , fd_(other.fd_)
#endif
    {
        other.bitmap_ = nullptr;
#ifdef _WIN32
        other.hFile_ = NULL;
        other.hMapFile_ = NULL;
#else
        other.fd_ = -1;
#endif
    }

    // Move assignment operator
    NativeCalendar& operator=(NativeCalendar&& other) noexcept {
        if (this != &other) {
            unmap_file();

            start_year_ = other.start_year_;
            bitmap_ = other.bitmap_;
            bitmap_size_ = other.bitmap_size_;
            year_offsets_ = std::move(other.year_offsets_);
#ifdef _WIN32
            hFile_ = other.hFile_;
            hMapFile_ = other.hMapFile_;
#else
            fd_ = other.fd_;
#endif

            other.bitmap_ = nullptr;
#ifdef _WIN32
            other.hFile_ = NULL;
            other.hMapFile_ = NULL;
#else
            other.fd_ = -1;
#endif
        }
        return *this;
    }

    bool is_trading_day(int year, int month, int day) const {
        int index = date_to_doy(year, month, day);
        if (index < 0 || index >= static_cast<int>(bitmap_size_)) {
            return false;
        }
        int byte_index = index / 8;
        int bit_index = index % 8;
        // 位序采用高位在前（MSB-first），与位图文件编码一致
        return ((bitmap_[byte_index] >> (7 - bit_index)) & 1) != 0;
    }

    std::optional<std::tuple<int, int, int>> get_next_trading_day(int year, int month, int day, bool include_self) const {
        int index = date_to_doy(year, month, day);
        if (index < 0) return std::nullopt;
        if (!include_self) {
            index++;
        }

        while (index < bitmap_size_) {
            auto date = doy_to_date(index);
            if (is_trading_day(std::get<0>(date), std::get<1>(date), std::get<2>(date))) {
                return date;
            }
            index++;
        }
        return std::nullopt;
    }

    std::optional<std::tuple<int, int, int>> get_previous_trading_day(int year, int month, int day, bool include_self) const {
        int index = date_to_doy(year, month, day);
        if (index < 0) return std::nullopt;
        if (!include_self) {
            index--;
        }

        while (index >= 0) {
            auto date = doy_to_date(index);
            if (is_trading_day(std::get<0>(date), std::get<1>(date), std::get<2>(date))) {
                return date;
            }
            index--;
        }
        return std::nullopt;
    }

    std::vector<std::tuple<int, int, int>> get_trading_days_in_range(int start_year, int start_month, int start_day, int end_year, int end_month, int end_day) const {
        std::vector<std::tuple<int, int, int>> days;
        
        int start_index = date_to_doy(start_year, start_month, start_day);
        int end_index = date_to_doy(end_year, end_month, end_day);

        for (int i = start_index; i <= end_index; ++i) {
            if (i >= 0 && i < bitmap_size_) {
                auto date = doy_to_date(i);
                if (is_trading_day(std::get<0>(date), std::get<1>(date), std::get<2>(date))) {
                    days.push_back(date);
                }
            }
        }
        return days;
    }

private:
    bool is_leap(int year) const {
        return (year % 4 == 0 && year % 100 != 0) || (year % 400 == 0);
    }

    int date_to_doy(int year, int month, int day) const {
        // Calculate day of year (doy)
        static const int days_before[13] = {0, 0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334};
        int doy = days_before[month] + day;
        if (month > 2 && is_leap(year)) {
            doy++;
        }

        int year_index = year - start_year_;
        if (year_index < 0 || year_index >= static_cast<int>(year_offsets_.size())) {
            std::string details = "year=" + std::to_string(year) + ", start_year=" + std::to_string(start_year_);
            CALENDAR_LOG_WARNING("Requested date outside of calendar range", details.c_str());
            return -1; // Invalid index for out-of-bounds year
        }

        return year_offsets_[year_index] + doy - 1;
    }

    std::tuple<int, int, int> doy_to_date(int index) const {
        int year = start_year_;
        while (year - start_year_ + 1 < year_offsets_.size() && index >= year_offsets_[year - start_year_ + 1]) {
            year++;
        }
        int doy = index - year_offsets_[year - start_year_] + 1;

        static const int days_in_month[13] = {0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
        int month = 1;
        while (doy > days_in_month[month] + (month == 2 && is_leap(year))) {
            doy -= days_in_month[month] + (month == 2 && is_leap(year));
            month++;
        }
        return {year, month, doy};
    }
};

PYBIND11_MODULE(_native_calendar, m) {
    py::class_<NativeCalendar>(m, "NativeCalendar")
        .def(py::init<int, const std::string&>())
        .def("is_trading_day", &NativeCalendar::is_trading_day)
        .def("get_next_trading_day", &NativeCalendar::get_next_trading_day)
        .def("get_previous_trading_day", &NativeCalendar::get_previous_trading_day)
        .def("get_trading_days_in_range", &NativeCalendar::get_trading_days_in_range);

    native_log_bridge_log(
        NATIVE_LOG_LEVEL_INFO,
        CALENDAR_MODULE_COMPONENT,
        "calendar_module_init",
        __LINE__,
        "native_calendar module initialized",
        nullptr);
}