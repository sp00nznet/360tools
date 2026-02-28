#!/usr/bin/env python3
"""Parse XEX2 import table and resolve kernel/XAM ordinals to function names."""

import struct
import sys

# Known Xbox 360 kernel ordinal names (from Xenia source)
XBOXKRNL_ORDINALS = {
    3: 'DbgPrint', 9: 'ExAllocatePoolWithTag', 10: 'ExFreePool',
    11: 'ExGetXConfigSetting', 14: 'ExRegisterTitleTerminateNotification',
    16: 'ExTerminateThread', 24: 'HalReturnToFirmware',
    30: 'InterlockedFlushSList', 36: 'KeBugCheck', 37: 'KeBugCheckEx',
    46: 'KeDelayExecutionThread', 51: 'KeEnterCriticalRegion',
    52: 'KeGetCurrentProcessType', 62: 'KeInitializeDpc',
    63: 'KeInitializeEvent', 69: 'KeInitializeTimerEx',
    73: 'KeLeaveCriticalRegion', 78: 'KeQueryPerformanceFrequency',
    89: 'KeRaiseIrqlToDpcLevel', 93: 'KeResetEvent',
    94: 'KeRestoreFloatingPointState', 96: 'KeResumeThread',
    98: 'KeSaveFloatingPointState', 100: 'KeSetAffinityThread',
    101: 'KeSetBasePriorityThread', 103: 'KeSetEvent',
    107: 'KeSetTimerEx', 109: 'KeStallExecutionProcessor',
    110: 'KeSuspendThread', 113: 'KeTlsAlloc', 114: 'KeTlsFree',
    115: 'KeTlsGetValue', 116: 'KeTlsSetValue',
    119: 'KeWaitForMultipleObjects', 120: 'KeWaitForSingleObject',
    141: 'MmAllocatePhysicalMemoryEx', 142: 'MmFreePhysicalMemory',
    150: 'MmQueryAddressProtect', 155: 'MmSetAddressProtect',
    157: 'NtAllocateVirtualMemory', 160: 'NtClose', 161: 'NtCreateEvent',
    162: 'NtCreateFile', 163: 'NtCreateMutant', 166: 'NtCreateSemaphore',
    176: 'NtFreeVirtualMemory', 180: 'NtOpenFile',
    190: 'NtQueryInformationFile', 196: 'NtQueryVirtualMemory',
    198: 'NtReadFile', 200: 'NtReleaseMutant', 201: 'NtReleaseSemaphore',
    204: 'NtResumeThread', 207: 'NtSetEvent',
    208: 'NtSetInformationFile', 210: 'NtSetTimerResolution',
    214: 'NtSuspendThread', 219: 'NtWaitForSingleObjectEx',
    222: 'NtWriteFile', 224: 'ObDereferenceObject',
    226: 'ObReferenceObject', 227: 'ObReferenceObjectByHandle',
    229: 'ObReferenceObjectByName', 281: 'RtlCompareMemory',
    283: 'RtlEnterCriticalSection', 286: 'RtlInitAnsiString',
    291: 'RtlInitializeCriticalSection', 294: 'RtlLeaveCriticalSection',
    299: 'RtlNtStatusToDosError', 304: 'RtlUnicodeToMultiByteN',
    307: 'sprintf', 308: 'DbgPrint', 312: 'strchr', 313: 'strcmp',
    315: 'strlen', 317: 'strncpy', 320: 'tolower',
    323: 'vsnprintf', 324: 'vsprintf',
    326: 'ExCreateThread', 330: 'KeInitializeApc',
    331: 'KeInsertQueueApc', 332: 'KeRemoveQueueDpc',
    334: 'KfAcquireSpinLock', 335: 'KfReleaseSpinLock',
    343: 'NtQueueApcThread', 348: 'KeSetCurrentStackPointers',
    349: 'KeSetDisableBoostThread',
    406: 'VdEnableDisableClockGating', 409: 'VdGetCurrentDisplayGamma',
    410: 'VdGetCurrentDisplayInformation', 414: 'VdInitializeRingBuffer',
    416: 'VdInitializeScaler', 418: 'VdIsHSIOTrainingSucceeded',
    419: 'VdPersistDisplay', 420: 'VdQueryVideoFlags',
    421: 'VdQueryVideoMode', 422: 'VdCallGraphicsNotificationRoutines',
    424: 'VdSetDisplayMode', 425: 'VdSetGraphicsInterruptCallback',
    426: 'VdSetSystemCommandBufferGpuIdentifierAddress',
    427: 'VdInitializeEngines', 430: 'VdSwap',
    432: 'VdEnableRingBufferRPtrWriteBack', 434: 'VdGetSystemCommandBuffer',
    436: 'VdSetHSIOCalibrationMode', 438: 'VdInitializeScalerCommandBuffer',
    454: 'XAudioGetSpeakerConfig', 455: 'XAudioGetVoiceCategoryVolumeChangeMask',
    456: 'XAudioRegisterRenderDriverClient', 457: 'XAudioUnregisterRenderDriverClient',
    458: 'XAudioSubmitRenderDriverFrame', 459: 'XAudioSetDriverHook',
    614: 'XexCheckExecutablePrivilege', 607: 'XexGetProcedureAddress',
    608: 'XexGetModuleHandle', 609: 'XexGetModuleSection',
    640: 'XInputGetCapabilities', 641: 'XInputGetState',
    643: 'XInputSetState',
}

XAM_ORDINALS = {
    1: 'XamGetSystemVersion',
    3: 'XamEnumerate', 4: 'XamContentCreate',
    5: 'XamContentClose', 6: 'XamContentFlush',
    9: 'XamContentCreateEnumerator',
    15: 'XamShowGamerCardUI', 18: 'XamShowMessageComposeUI',
    19: 'XamShowFriendsUI', 20: 'XamShowAchievementsUI',
    21: 'XamShowMarketplaceUI',
    24: 'XamShowPlayersUI', 25: 'XamShowSigninUI',
    70: 'XamUserGetXUID', 72: 'XamUserGetSigninState',
    73: 'XamUserGetSigninInfo', 74: 'XamUserGetName',
    75: 'XamUserCheckPrivilege', 79: 'XamUserIsOnlineEnabled',
    80: 'XamUserGetMembershipTier',
    399: 'XamNotifyCreateListener', 400: 'XamNotifyWait',
    403: 'XamNotifyDestroyListener',
    505: 'XamInputGetState', 506: 'XamInputGetCapabilities',
    507: 'XamInputSetState',
    651: 'XamTaskSchedule', 652: 'XamTaskShouldExit',
    653: 'XamTaskGetResult',
    723: 'XamShowSigninUI',
}


def parse_xex_imports(xex_path):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    with open(xex_path, 'rb') as f:
        data = f.read()

    magic = data[0:4]
    assert magic == b'XEX2', f"Not a XEX2 file: {magic}"

    # Find import libraries optional header
    num_opt_headers = struct.unpack_from('>I', data, 0x14)[0]
    imp_offset = None
    off = 0x18
    for i in range(num_opt_headers):
        key = struct.unpack_from('>I', data, off)[0]
        value = struct.unpack_from('>I', data, off + 4)[0]
        if key == 0x000103FF:
            imp_offset = value
        off += 8

    if imp_offset is None:
        print("No import library header found!")
        return

    # Parse import library block
    # Format: total_size(4) | string_table_size(4) | library_count(4) | strings... | libraries...
    total_size = struct.unpack_from('>I', data, imp_offset)[0]
    str_table_size = struct.unpack_from('>I', data, imp_offset + 4)[0]
    lib_count = struct.unpack_from('>I', data, imp_offset + 8)[0]

    print(f"Import libraries: {lib_count}")
    print(f"Total import block: 0x{total_size:X} bytes")
    print(f"String table: {str_table_size} bytes")

    # Read string table
    str_start = imp_offset + 12
    str_data = data[str_start:str_start + str_table_size]
    strs = []
    pos = 0
    while pos < len(str_data):
        end = str_data.find(b'\x00', pos)
        if end == -1:
            break
        s = str_data[pos:end].decode('ascii', errors='replace')
        if s:
            strs.append(s)
        pos = end + 1
        # Align to 4 bytes
        while pos < len(str_data) and pos % 4 != 0:
            pos += 1

    print(f"Libraries found: {strs}")
    print()

    # Parse each library
    lib_off = str_start + str_table_size
    all_imports = {}
    for j in range(lib_count):
        lib_size = struct.unpack_from('>I', data, lib_off)[0]
        # Bytes 4-24: SHA1 digest
        import_id = struct.unpack_from('>I', data, lib_off + 24)[0]
        version = struct.unpack_from('>I', data, lib_off + 28)[0]
        version_min = struct.unpack_from('>I', data, lib_off + 32)[0]
        name_index = struct.unpack_from('>H', data, lib_off + 36)[0]
        num_records = struct.unpack_from('>H', data, lib_off + 38)[0]

        lib_name = strs[name_index] if name_index < len(strs) else f'lib_{name_index}'
        v_major = (version >> 24) & 0xFF
        v_minor = (version >> 16) & 0xFF
        v_build = version & 0xFFFF

        # Pick ordinal database
        if 'xboxkrnl' in lib_name.lower():
            ordinal_db = XBOXKRNL_ORDINALS
        elif 'xam' in lib_name.lower():
            ordinal_db = XAM_ORDINALS
        else:
            ordinal_db = {}

        print(f"=== {lib_name} (v{v_major}.{v_minor}.{v_build}) ===")
        print(f"    Records: {num_records}")

        imports = []
        rec_off = lib_off + 40
        # Records come in pairs: (ordinal_record, thunk_address)
        # The ordinal record has the ordinal in bits 0-15
        # The thunk address record has the guest address
        r = 0
        while r < num_records:
            record = struct.unpack_from('>I', data, rec_off)[0]
            ordinal = record & 0xFFFF
            rec_type = (record >> 24) & 0xFF

            # Get thunk address from next record if available
            thunk_addr = 0
            if r + 1 < num_records:
                thunk_addr = struct.unpack_from('>I', data, rec_off + 4)[0]

            name = ordinal_db.get(ordinal, f'ordinal_{ordinal}')
            imports.append((ordinal, name, thunk_addr))
            if thunk_addr:
                print(f"    #{ordinal:4d}: {name:40s} (thunk=0x{thunk_addr:08X})")
            else:
                print(f"    #{ordinal:4d}: {name}")

            rec_off += 8  # skip both ordinal and thunk records
            r += 2

        all_imports[lib_name] = imports
        print()
        lib_off += lib_size

    return all_imports


if __name__ == '__main__':
    xex = sys.argv[1] if len(sys.argv) > 1 else 'extracted/default.xex'
    parse_xex_imports(xex)
