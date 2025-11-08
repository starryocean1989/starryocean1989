#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <Windows.h>
#include <winioctl.h>
#include <ntdddisk.h>
#include <wchar.h>
#include <stdint.h>

#ifndef CAP_SMART_CMD
#define CAP_SMART_CMD 0x0001
#endif

#ifndef SMART_GET_VERSION
#define SMART_GET_VERSION CTL_CODE(FILE_DEVICE_DISK, 0x0020, METHOD_BUFFERED, FILE_READ_ACCESS)
#endif

#ifndef SMART_RCV_DRIVE_DATA
#define SMART_RCV_DRIVE_DATA CTL_CODE(FILE_DEVICE_DISK, 0x0022, METHOD_BUFFERED, FILE_READ_ACCESS | FILE_WRITE_ACCESS)
#endif

#ifndef READ_ATTRIBUTE_BUFFER_SIZE
#define READ_ATTRIBUTE_BUFFER_SIZE 512
#endif

#ifndef SMART_CMD
#define SMART_CMD 0xB0
#endif

#ifndef READ_ATTRIBUTES
#define READ_ATTRIBUTES 0xD0
#endif

#ifndef SMART_CYL_LOW
#define SMART_CYL_LOW 0x4F
#endif

#ifndef SMART_CYL_HIGH
#define SMART_CYL_HIGH 0xC2
#endif

#ifndef StorageDeviceTemperatureProperty
#define StorageDeviceTemperatureProperty ((STORAGE_PROPERTY_ID)27)
#endif

typedef struct _SMART_SUMMARY {
    PyObject *attributes;          /* Python list of attribute dicts */
    int       has_temperature;
    double    temperature_c;
    uint64_t  reallocated;
    uint64_t  pending;
    uint64_t  uncorrectable;
    uint64_t  power_on_hours;
} SMART_SUMMARY;

#define SAFE_FREE(ptr) \
    do {               \
        if ((ptr) != NULL) { \
            free(ptr);       \
            ptr = NULL;      \
        }                    \
    } while (0)

static size_t
_safe_strnlen(const char *str, size_t max_len)
{
    size_t idx = 0;
    if (str == NULL) {
        return 0;
    }
    while (idx < max_len && str[idx] != '\0') {
        idx++;
    }
    return idx;
}

static PyObject *
decode_descriptor_field(const BYTE *buffer, DWORD offset, DWORD total_length)
{
    if (!buffer || offset == 0 || offset == 0xFFFFFFFF || offset >= total_length) {
        return Py_NewRef(Py_None);
    }

    const char *ptr = (const char *)(buffer + offset);
    size_t max_len = total_length - offset;
    size_t length = _safe_strnlen(ptr, max_len);
    if (length == 0) {
        return Py_NewRef(Py_None);
    }

    return PyUnicode_Decode(ptr, (Py_ssize_t)length, "utf-8", "ignore");
}

static const char *
bus_type_to_string(STORAGE_BUS_TYPE bus_type)
{
    switch (bus_type) {
        case BusTypeScsi:
            return "scsi";
        case BusTypeAtapi:
            return "atapi";
        case BusTypeAta:
            return "ata";
        case BusType1394:
            return "ieee1394";
        case BusTypeSsa:
            return "ssa";
        case BusTypeFibre:
            return "fibre";
        case BusTypeUsb:
            return "usb";
        case BusTypeRAID:
            return "raid";
        case BusTypeiScsi:
            return "iscsi";
        case BusTypeSas:
            return "sas";
        case BusTypeSata:
            return "sata";
        case BusTypeSd:
            return "sd";
        case BusTypeMmc:
            return "mmc";
        case BusTypeVirtual:
            return "virtual";
        case BusTypeFileBackedVirtual:
            return "file_virtual";
        case BusTypeSpaces:
            return "storage_spaces";
        case BusTypeNvme:
            return "nvme";
        case BusTypeSCM:
            return "scm";
        case BusTypeUfs:
            return "ufs";
        default:
            return "unknown";
    }
}

static PyObject *
format_capacity_string(LONGLONG size_bytes)
{
    if (size_bytes <= 0) {
        return PyUnicode_FromString("Unknown");
    }

    double size_gb = (double)size_bytes / (1024.0 * 1024.0 * 1024.0);
    char buffer[32];
    if (size_gb >= 1024.0) {
        double size_tb = size_gb / 1024.0;
        snprintf(buffer, sizeof(buffer), "%.2f TB", size_tb);
    } else {
        snprintf(buffer, sizeof(buffer), "%.1f GB", size_gb);
    }
    return PyUnicode_FromString(buffer);
}

static uint64_t
read_raw_value(const BYTE *raw_bytes)
{
    uint64_t value = 0;
    for (int idx = 0; idx < 6; ++idx) {
        value |= ((uint64_t)raw_bytes[idx]) << (idx * 8);
    }
    return value;
}

static int
collect_smart_attributes(const BYTE *buffer, DWORD buffer_size, SMART_SUMMARY *summary)
{
    if (summary == NULL) {
        return -1;
    }

    summary->attributes = PyList_New(0);
    if (summary->attributes == NULL) {
        return -1;
    }

    summary->has_temperature = 0;
    summary->temperature_c = 0.0;
    summary->reallocated = 0;
    summary->pending = 0;
    summary->uncorrectable = 0;
    summary->power_on_hours = 0;

    if (buffer == NULL || buffer_size < 2U) {
        return 0;
    }

    const BYTE *attr_ptr = buffer + 2;  /* 跳过版本信息 */
    DWORD attr_size = buffer_size - 2U;

    for (int attr_index = 0; attr_index < 30; ++attr_index) {
        DWORD offset = attr_index * 12U;
        if (offset + 12U > attr_size) {
            break;
        }

        const BYTE *entry = attr_ptr + offset;
        BYTE attribute_id = entry[0];
        if (attribute_id == 0 || attribute_id == 0xFF) {
            continue;
        }

        BYTE current_value = entry[3];
        BYTE worst_value = entry[4];
        uint64_t raw_value = read_raw_value(entry + 5);

        PyObject *attr_dict = Py_BuildValue(
            "{s:i,s:i,s:i,s:K}",
            "id",
            (int)attribute_id,
            "value",
            (int)current_value,
            "worst",
            (int)worst_value,
            "raw",
            raw_value
        );
        if (attr_dict == NULL) {
            Py_DECREF(summary->attributes);
            summary->attributes = NULL;
            return -1;
        }

        if (PyList_Append(summary->attributes, attr_dict) < 0) {
            Py_DECREF(attr_dict);
            Py_DECREF(summary->attributes);
            summary->attributes = NULL;
            return -1;
        }
        Py_DECREF(attr_dict);

        switch (attribute_id) {
            case 0x05:  /* Reallocated Sectors Count */
                summary->reallocated = raw_value;
                break;
            case 0x09:  /* Power-On Hours */
                summary->power_on_hours = raw_value;
                break;
            case 0xC0:  /* Unsafe Shutdown / Power-off retract */
            case 0xC3:  /* Hardware ECC Recovered */
            case 0xC5:  /* Current Pending Sector Count */
                summary->pending = raw_value;
                break;
            case 0xC6:  /* Uncorrectable Sector Count */
            case 0xBB:  /* Reported Uncorrectable Errors */
            case 0xBC:  /* Command Timeout */
            case 0xBD:  /* High Fly Writes */
            case 0xBE:  /* Airflow Temperature */
            case 0xBF:  /* G-sense Error Rate */
                summary->uncorrectable = raw_value;
                break;
            case 0xC2:  /* Temperature (some drives) */
            case 0xBE:  /* Temperature Alternate */
            case 0xB0:
            case 0xB1:
            case 0xB8:
            case 0xC7:
            case 0xC8:
                /* fallthrough to allow parsing attr 194 explicitly */
                break;
            case 0xC7:  /* CRC Error Count */
            default:
                break;
        }

        if (attribute_id == 0xC5) {
            summary->pending = raw_value;
        } else if (attribute_id == 0xC6 || attribute_id == 0xBB || attribute_id == 0xBC) {
            summary->uncorrectable = raw_value;
        } else if (attribute_id == 0x09) {
            summary->power_on_hours = raw_value;
        }

        if (attribute_id == 0xC2 || attribute_id == 0xBE || attribute_id == 0xB8 || attribute_id == 0xB0 || attribute_id == 0xC8 || attribute_id == 0x194) {
            /* 0x194 (十进制 194) 是常见温度属性 */
            if (attribute_id == 0x194 || attribute_id == 0xC2 || attribute_id == 0xBE) {
                double temp_c = (double)(raw_value & 0xFF);
                summary->temperature_c = temp_c;
                summary->has_temperature = 1;
            }
        }

        if (attribute_id == 0x05) {
            summary->reallocated = raw_value;
        } else if (attribute_id == 0xC5) {
            summary->pending = raw_value;
        } else if (attribute_id == 0xC6 || attribute_id == 0xBB || attribute_id == 0xBC) {
            summary->uncorrectable = raw_value;
        }
    }

    return 0;
}

static int
issue_smart_read_attributes(HANDLE handle, int physical_drive_number, SMART_SUMMARY *summary)
{
    DWORD bytes_returned = 0;
    GETVERSIONINPARAMS version_params;
    ZeroMemory(&version_params, sizeof(version_params));

    if (!DeviceIoControl(
            handle,
            SMART_GET_VERSION,
            NULL,
            0,
            &version_params,
            sizeof(version_params),
            &bytes_returned,
            NULL)) {
        return 0;  /* SMART 不支持 */
    }

    if (!(version_params.fCapabilities & CAP_SMART_CMD)) {
        return 0;
    }

    DWORD out_buffer_size = sizeof(SENDCMDOUTPARAMS) + READ_ATTRIBUTE_BUFFER_SIZE;
    SENDCMDOUTPARAMS *out_params = (SENDCMDOUTPARAMS *)malloc(out_buffer_size);
    if (out_params == NULL) {
        PyErr_NoMemory();
        return -1;
    }
    ZeroMemory(out_params, out_buffer_size);

    SENDCMDINPARAMS in_params;
    ZeroMemory(&in_params, sizeof(in_params));
    in_params.cBufferSize = READ_ATTRIBUTE_BUFFER_SIZE;
    in_params.irDriveRegs.bFeaturesReg = READ_ATTRIBUTES;
    in_params.irDriveRegs.bSectorCountReg = 1;
    in_params.irDriveRegs.bSectorNumberReg = 1;
    in_params.irDriveRegs.bCylLowReg = SMART_CYL_LOW;
    in_params.irDriveRegs.bCylHighReg = SMART_CYL_HIGH;
    in_params.irDriveRegs.bCommandReg = SMART_CMD;
    in_params.irDriveRegs.bDriveHeadReg = (BYTE)(0xA0 | ((physical_drive_number & 1) << 4));
    in_params.bDriveNumber = (BYTE)physical_drive_number;

    if (!DeviceIoControl(
            handle,
            SMART_RCV_DRIVE_DATA,
            &in_params,
            sizeof(in_params),
            out_params,
            out_buffer_size,
            &bytes_returned,
            NULL)) {
        SAFE_FREE(out_params);
        return 0;
    }

    int parse_result = collect_smart_attributes(out_params->bBuffer, READ_ATTRIBUTE_BUFFER_SIZE, summary);
    SAFE_FREE(out_params);
    return parse_result;
}

static int
query_device_descriptor(
    HANDLE handle,
    PyObject **model,
    PyObject **serial,
    PyObject **vendor,
    PyObject **product,
    const char **bus_type_str)
{
    BYTE buffer[1024];
    STORAGE_PROPERTY_QUERY query;
    ZeroMemory(&query, sizeof(query));
    ZeroMemory(buffer, sizeof(buffer));
    query.PropertyId = StorageDeviceProperty;
    query.QueryType = PropertyStandardQuery;

    DWORD bytes_returned = 0;
    if (!DeviceIoControl(
            handle,
            IOCTL_STORAGE_QUERY_PROPERTY,
            &query,
            sizeof(query),
            buffer,
            sizeof(buffer),
            &bytes_returned,
            NULL)) {
        *model = PyUnicode_FromString("Unknown");
        *serial = PyUnicode_FromString("Unknown");
        *vendor = Py_NewRef(Py_None);
        *product = Py_NewRef(Py_None);
        *bus_type_str = "unknown";
        return 0;
    }

    STORAGE_DEVICE_DESCRIPTOR *descriptor = (STORAGE_DEVICE_DESCRIPTOR *)buffer;
    *model = decode_descriptor_field(buffer, descriptor->ProductIdOffset, bytes_returned);
    *serial = decode_descriptor_field(buffer, descriptor->SerialNumberOffset, bytes_returned);
    *vendor = decode_descriptor_field(buffer, descriptor->VendorIdOffset, bytes_returned);
    *product = decode_descriptor_field(buffer, descriptor->ProductRevisionOffset, bytes_returned);
    *bus_type_str = bus_type_to_string(descriptor->BusType);
    return 0;
}

static int
query_disk_size(HANDLE handle, PyObject **size_bytes_obj, PyObject **capacity_str)
{
    GET_LENGTH_INFORMATION length_info;
    DWORD bytes_returned = 0;
    if (!DeviceIoControl(
            handle,
            IOCTL_DISK_GET_LENGTH_INFO,
            NULL,
            0,
            &length_info,
            sizeof(length_info),
            &bytes_returned,
            NULL)) {
        *size_bytes_obj = PyLong_FromLong(0);
        *capacity_str = PyUnicode_FromString("Unknown");
        return 0;
    }

    LONGLONG size_bytes = length_info.Length.QuadPart;
    *size_bytes_obj = PyLong_FromLongLong((long long)size_bytes);
    *capacity_str = format_capacity_string(size_bytes);
    return 0;
}

static const wchar_t *
build_physical_drive_path(int drive_index, wchar_t *buffer, size_t buffer_len)
{
    if (buffer == NULL || buffer_len == 0) {
        return NULL;
    }
#ifdef _MSC_VER
    _snwprintf_s(buffer, buffer_len, _TRUNCATE, L"\\\\.\\PhysicalDrive%d", drive_index);
#else
    swprintf(buffer, buffer_len, L"\\\\.\\PhysicalDrive%d", drive_index);
#endif
    buffer[buffer_len - 1] = L'\0';
    return buffer;
}

static PyObject *
build_drive_entry(int drive_index, HANDLE handle)
{
    SMART_SUMMARY summary;
    ZeroMemory(&summary, sizeof(summary));

    int smart_status = issue_smart_read_attributes(handle, drive_index, &summary);
    if (smart_status < 0) {
        return NULL;
    }

    PyObject *model = NULL;
    PyObject *serial = NULL;
    PyObject *vendor = NULL;
    PyObject *product = NULL;
    const char *bus_type = "unknown";
    if (query_device_descriptor(handle, &model, &serial, &vendor, &product, &bus_type) < 0) {
        Py_XDECREF(summary.attributes);
        return NULL;
    }

    PyObject *size_bytes_obj = NULL;
    PyObject *capacity_str = NULL;
    if (query_disk_size(handle, &size_bytes_obj, &capacity_str) < 0) {
        Py_DECREF(model);
        Py_DECREF(serial);
        Py_DECREF(vendor);
        Py_DECREF(product);
        Py_XDECREF(summary.attributes);
        return NULL;
    }

    wchar_t device_path[64];
    build_physical_drive_path(drive_index, device_path, sizeof(device_path) / sizeof(device_path[0]));
    PyObject *device_path_obj = PyUnicode_FromWideChar(device_path, -1);
    if (device_path_obj == NULL) {
        Py_DECREF(model);
        Py_DECREF(serial);
        Py_DECREF(vendor);
        Py_DECREF(product);
        Py_DECREF(size_bytes_obj);
        Py_DECREF(capacity_str);
        Py_XDECREF(summary.attributes);
        return NULL;
    }

    PyObject *entry = PyDict_New();
    if (entry == NULL) {
        Py_DECREF(device_path_obj);
        Py_DECREF(model);
        Py_DECREF(serial);
        Py_DECREF(vendor);
        Py_DECREF(product);
        Py_DECREF(size_bytes_obj);
        Py_DECREF(capacity_str);
        Py_XDECREF(summary.attributes);
        return NULL;
    }

    PyObject *drive_index_obj = PyLong_FromLong(drive_index);
    if (!drive_index_obj || PyDict_SetItemString(entry, "drive_index", drive_index_obj) < 0) {
        Py_XDECREF(drive_index_obj);
        Py_DECREF(entry);
        Py_DECREF(device_path_obj);
        Py_DECREF(model);
        Py_DECREF(serial);
        Py_DECREF(vendor);
        Py_DECREF(product);
        Py_DECREF(size_bytes_obj);
        Py_DECREF(capacity_str);
        Py_XDECREF(summary.attributes);
        return NULL;
    }
    Py_DECREF(drive_index_obj);

    if (PyDict_SetItemString(entry, "device_path", device_path_obj) < 0) {
        Py_DECREF(entry);
        Py_DECREF(device_path_obj);
        Py_DECREF(model);
        Py_DECREF(serial);
        Py_DECREF(vendor);
        Py_DECREF(product);
        Py_DECREF(size_bytes_obj);
        Py_DECREF(capacity_str);
        Py_XDECREF(summary.attributes);
        return NULL;
    }
    Py_DECREF(device_path_obj);

    if (PyDict_SetItemString(entry, "model", model) < 0 ||
        PyDict_SetItemString(entry, "serial_number", serial) < 0 ||
        PyDict_SetItemString(entry, "vendor", vendor) < 0 ||
        PyDict_SetItemString(entry, "product_revision", product) < 0) {
        Py_DECREF(entry);
        Py_DECREF(model);
        Py_DECREF(serial);
        Py_DECREF(vendor);
        Py_DECREF(product);
        Py_DECREF(size_bytes_obj);
        Py_DECREF(capacity_str);
        Py_XDECREF(summary.attributes);
        return NULL;
    }
    Py_DECREF(model);
    Py_DECREF(serial);
    Py_DECREF(vendor);
    Py_DECREF(product);

    PyObject *bus_type_obj = PyUnicode_FromString(bus_type);
    if (bus_type_obj == NULL) {
        Py_DECREF(entry);
        Py_DECREF(size_bytes_obj);
        Py_DECREF(capacity_str);
        Py_XDECREF(summary.attributes);
        return NULL;
    }
    if (PyDict_SetItemString(entry, "bus_type", bus_type_obj) < 0) {
        Py_DECREF(bus_type_obj);
        Py_DECREF(entry);
        Py_DECREF(size_bytes_obj);
        Py_DECREF(capacity_str);
        Py_XDECREF(summary.attributes);
        return NULL;
    }
    Py_DECREF(bus_type_obj);

    if (PyDict_SetItemString(entry, "size_bytes", size_bytes_obj) < 0 ||
        PyDict_SetItemString(entry, "capacity", capacity_str) < 0) {
        Py_DECREF(entry);
        Py_DECREF(size_bytes_obj);
        Py_DECREF(capacity_str);
        Py_XDECREF(summary.attributes);
        return NULL;
    }
    Py_DECREF(size_bytes_obj);
    Py_DECREF(capacity_str);

    int smart_supported = (smart_status >= 0 && summary.attributes != NULL);
    PyObject *smart_supported_obj = PyBool_FromLong(smart_supported ? 1 : 0);
    if (!smart_supported_obj || PyDict_SetItemString(entry, "smart_supported", smart_supported_obj) < 0) {
        Py_XDECREF(smart_supported_obj);
        Py_DECREF(entry);
        Py_XDECREF(summary.attributes);
        return NULL;
    }
    Py_DECREF(smart_supported_obj);

    double warning_threshold = 75.0;
    double critical_threshold = 85.0;
    if (summary.has_temperature) {
        PyObject *temp_value = PyFloat_FromDouble(summary.temperature_c);
        if (!temp_value || PyDict_SetItemString(entry, "temperature_celsius", temp_value) < 0) {
            Py_XDECREF(temp_value);
            Py_DECREF(entry);
            Py_XDECREF(summary.attributes);
            return NULL;
        }
        Py_DECREF(temp_value);
    } else {
        if (PyDict_SetItemString(entry, "temperature_celsius", Py_None) < 0) {
            Py_DECREF(entry);
            Py_XDECREF(summary.attributes);
            return NULL;
        }
    }

    PyObject *warning_obj = PyFloat_FromDouble(warning_threshold);
    PyObject *critical_obj = PyFloat_FromDouble(critical_threshold);
    if (!warning_obj || !critical_obj ||
        PyDict_SetItemString(entry, "warning_threshold_celsius", warning_obj) < 0 ||
        PyDict_SetItemString(entry, "critical_threshold_celsius", critical_obj) < 0) {
        Py_XDECREF(warning_obj);
        Py_XDECREF(critical_obj);
        Py_DECREF(entry);
        Py_XDECREF(summary.attributes);
        return NULL;
    }
    Py_DECREF(warning_obj);
    Py_DECREF(critical_obj);

    PyObject *reallocated_obj = PyLong_FromUnsignedLongLong(summary.reallocated);
    PyObject *pending_obj = PyLong_FromUnsignedLongLong(summary.pending);
    PyObject *uncorrectable_obj = PyLong_FromUnsignedLongLong(summary.uncorrectable);
    PyObject *power_on_obj = PyLong_FromUnsignedLongLong(summary.power_on_hours);
    if (!reallocated_obj || !pending_obj || !uncorrectable_obj || !power_on_obj ||
        PyDict_SetItemString(entry, "reallocated_sectors", reallocated_obj) < 0 ||
        PyDict_SetItemString(entry, "pending_sectors", pending_obj) < 0 ||
        PyDict_SetItemString(entry, "uncorrectable_errors", uncorrectable_obj) < 0 ||
        PyDict_SetItemString(entry, "power_on_hours", power_on_obj) < 0) {
        Py_XDECREF(reallocated_obj);
        Py_XDECREF(pending_obj);
        Py_XDECREF(uncorrectable_obj);
        Py_XDECREF(power_on_obj);
        Py_DECREF(entry);
        Py_XDECREF(summary.attributes);
        return NULL;
    }
    Py_DECREF(reallocated_obj);
    Py_DECREF(pending_obj);
    Py_DECREF(uncorrectable_obj);
    Py_DECREF(power_on_obj);

    const char *status_str = "unavailable";
    if (smart_supported) {
        status_str = "ok";
        if (summary.has_temperature && summary.temperature_c >= critical_threshold) {
            status_str = "critical";
        } else if (summary.has_temperature && summary.temperature_c >= warning_threshold) {
            status_str = "warning";
        }
        if (summary.reallocated > 0 || summary.pending > 0 || summary.uncorrectable > 0) {
            if (summary.uncorrectable > 0 || summary.pending > 10) {
                status_str = "critical";
            } else if (summary.reallocated > 0 || summary.pending > 0) {
                if (status_str != "critical") {
                    status_str = "warning";
                }
            }
        }
    }

    PyObject *status_obj = PyUnicode_FromString(status_str);
    if (!status_obj || PyDict_SetItemString(entry, "status", status_obj) < 0) {
        Py_XDECREF(status_obj);
        Py_DECREF(entry);
        Py_XDECREF(summary.attributes);
        return NULL;
    }
    Py_DECREF(status_obj);

    if (summary.attributes != NULL) {
        if (PyDict_SetItemString(entry, "attributes", summary.attributes) < 0) {
            Py_DECREF(entry);
            Py_DECREF(summary.attributes);
            return NULL;
        }
        Py_DECREF(summary.attributes);
    } else {
        if (PyDict_SetItemString(entry, "attributes", PyList_New(0)) < 0) {
            Py_DECREF(entry);
            return NULL;
        }
    }

    return entry;
}

static PyObject *
native_get_drive_temperature_data(PyObject *Py_UNUSED(self), PyObject *Py_UNUSED(args))
{
    PyObject *result = PyList_New(0);
    if (result == NULL) {
        return NULL;
    }

    for (int drive_index = 0; drive_index < 64; ++drive_index) {
        wchar_t device_path[64];
        build_physical_drive_path(drive_index, device_path, sizeof(device_path) / sizeof(device_path[0]));

        HANDLE handle = CreateFileW(
            device_path,
            GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            NULL,
            OPEN_EXISTING,
            0,
            NULL);

        if (handle == INVALID_HANDLE_VALUE) {
            continue;
        }

        PyObject *entry = build_drive_entry(drive_index, handle);
        CloseHandle(handle);

        if (entry == NULL) {
            Py_DECREF(result);
            return NULL;
        }

        if (PyList_Append(result, entry) < 0) {
            Py_DECREF(entry);
            Py_DECREF(result);
            return NULL;
        }
        Py_DECREF(entry);
    }

    return result;
}

PyDoc_STRVAR(
    native_get_drive_temperature_data_doc,
    "get_drive_temperature_data() -> List[Dict]\n"
    "\n"
    "枚举本地物理磁盘并返回 SMART / 温度 信息。");

static PyMethodDef NativeSmartMonitorMethods[] = {
    {"get_drive_temperature_data",
     (PyCFunction)native_get_drive_temperature_data,
     METH_NOARGS,
     native_get_drive_temperature_data_doc},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef native_smart_monitor_module = {
    PyModuleDef_HEAD_INIT,
    "native_smart_monitor",
    "Native SMART monitor helpers",
    -1,
    NativeSmartMonitorMethods,
    NULL,
    NULL,
    NULL,
    NULL
};

PyMODINIT_FUNC
PyInit_native_smart_monitor(void)
{
    PyObject *module = PyModule_Create(&native_smart_monitor_module);
    if (module == NULL) {
        return NULL;
    }

    if (PyModule_AddIntConstant(module, "SMART_MONITOR_AVAILABLE", 1) < 0) {
        Py_DECREF(module);
        return NULL;
    }

    return module;
}


