# Common Coding Pitfalls

Frequent errors to avoid in development sessions.

---

## Python: Async Generator Return Error

**Error:** `SyntaxError: 'return' with value in async generator`

**Cause:** Using `return value` in a function that contains `yield` statements.

**Wrong:**
```python
async def handler(self):
    if not valid:
        return rx.toast.error("message")  # ❌
    yield
```

**Correct:**
```python
async def handler(self):
    if not valid:
        yield rx.toast.error("message")  # ✅
        return
    yield
```

**Rule:** Functions with `yield` are generators. Use `yield` to return values, plain `return` to exit.

---

## Python: Yield From in Async Functions

**Error:** `SyntaxError: 'yield from' inside async function` or `TypeError: 'async for' requires an object with __aiter__ method, got generator`

**Cause:** Using wrong iteration method for generator type.

**Wrong:**
```python
async def handler(self):
    yield from self.regular_generator()  # ❌ SyntaxError
    async for x in self.regular_generator():  # ❌ TypeError
        yield x
```

**Correct:**
```python
async def handler(self):
    # For regular generators (def without async)
    for result in self.regular_generator():  # ✅
        yield result
    
    # For async generators (async def)
    async for result in self.async_generator():  # ✅
        yield result
```

**Rule:** In async functions, use `for` for regular generators, `async for` for async generators. Never use `yield from`.

---

## Rust/Tauri: Sidecar Binary Naming

**Error:** `Couldn't find binary 'ffmpeg' for target triple...`

**Cause:** Tauri requires bundled binaries to have target triple suffix.

**Wrong:**
```
src-tauri/binaries/ffmpeg
```

**Correct:**
```
src-tauri/binaries/ffmpeg-aarch64-apple-darwin     (macOS Silicon)
src-tauri/binaries/ffmpeg-x86_64-apple-darwin      (macOS Intel)
src-tauri/binaries/ffmpeg-x86_64-pc-windows-msvc.exe
```

**Rule:** Always suffix sidecar binaries with the full target triple. Tauri resolves the correct binary at runtime.

---

## Reflex: Segmented Control on_change Type

**Error:** `EventHandlerArgTypeMismatchError: Event handler on_change expects str | list[str] for argument value but got <class 'str'>`

**Cause:** Reflex segmented_control passes `str | list[str]` to on_change handlers.

**Wrong:**
```python
def set_processing_target(self, value: str):  # ❌
    self.processing_target = value
```

**Correct:**
```python
def set_processing_target(self, value: str | list[str]):  # ✅
    target = value[0] if isinstance(value, list) else value
    self.processing_target = target
```

**Rule:** Always type segmented_control handlers as `str | list[str]` and handle both cases.

---

