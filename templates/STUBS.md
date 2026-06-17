# Kernel stub & override playbook (ReXGlue v0.8.0)

When a recompiled title links/runs, it calls Xbox 360 kernel/XAM functions. Most
are implemented by `rexruntime`. The two situations you'll handle yourself:

## 1. Missing API — link fails with `undefined symbol` (the common, safe case)

The game imports a function `rexruntime.dll` doesn't export. The link error looks
like:

```
lld-link: error: undefined symbol: __declspec(dllimport) _XUsbcamCreate
  >>> referenced by ... PPCFuncMappings
```

Fix: define it in your project's `src/stubs.cpp` (see `overlay/src/stubs.cpp`)
using `<rex/hook.h>`, then add `stubs.cpp` to your CMake sources. One line per
missing symbol:

```cpp
REX_EXPORT_STUB(__imp__XFooBar);              // no-op, logs when called
REX_EXPORT_STUB_RETURN(__imp__XFooBar, 0);    // returns a fixed value in r3
```

For real behavior, write a typed entry function (args auto-marshal; `mapped_u32`,
`mapped_u64`, `mapped_void`, `ppc_ptr_t<T>` are guest pointers that byte-swap on
access) and register it:

```cpp
static u32 XFooBar_entry(u32 user_index, mapped_u32 out_ptr) {
  if (out_ptr) *out_ptr = 0;     // byte-swapped store into guest memory
  return X_E_SUCCESS;
}
REX_EXPORT(__imp__XFooBar, XFooBar_entry)
```

Tip: the SDK source is the best reference for signatures and return codes —
grep `src/kernel/` for the function name; many APIs are already implemented and
you can copy the `_entry` directly (that's exactly the XUsbcam case).

## 2. Override an API the SDK already implements

Two cases, both verified against the v0.8.0 SDK:

**(a) Override a recompiled guest function (`sub_XXXX`).** Codegen emits guest
functions weak (`DEFINE_REX_FUNC` → `REX_WEAK_FUNC`), so a strong project
definition of the same `sub_` wins with **no link flags**. Call the original
through its `__imp__sub_XXXX`. This is the game-logic-patch / license-bypass
pattern — see the comment block in `overlay/src/overrides.example.cpp`.

**(b) Override a kernel/XAM function the SDK exports** (e.g. force multi-user
sign-in). `rexruntime.dll` exports all symbols (`WINDOWS_EXPORT_ALL_SYMBOLS`), so
your definition collides with the import. Add **`/force:multiple`** to the link;
project objects link before the runtime import lib, so the first definition —
yours — wins:

```cmake
target_sources(mygame PRIVATE src/overrides.example.cpp)
if(WIN32)
  target_link_options(mygame PRIVATE "LINKER:/force:multiple")
endif()
```

Use `REX_HOOK(__imp__Name, entry_fn)` for these (defines + auto-marshals; *don't*
re-register with `REX_EXPORT` — the SDK already registered the name). Write the
`entry_fn` with the SDK's typed idiom (`mapped_*` / `ppc_ptr_t<T>` params, plain
return code) and `using namespace rex;` so the `X_E_*` codes resolve.
`overlay/src/overrides.example.cpp` is a verified, compiling port of the legacy
multi-user sign-in overrides (`XamUserGetSigninState/Info/XUID/Name`,
`XamShowSigninUI`).

## 3. Codegen analysis errors (not a stub — a manifest hint)

If `rexglue codegen` fails with `UnresolvedCall ... target not in any function`,
that's a function-boundary gap, not a missing stub. Add an `[entrypoint.functions]`
hint (see `overlay/manifest-overrides.example.toml`) — or just let the harness's
auto-resolve inject the hints for you.
