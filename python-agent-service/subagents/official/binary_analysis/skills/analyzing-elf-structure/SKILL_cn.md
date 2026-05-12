---
name: analyzing-elf-structure
description: |
  将 ELF（可执行与可链接格式）结构解析深度对齐 FR-04 / IR-09 对 PE 清单（Gap-02）
  和 Mach-O 解析器（Gap-01）的要求。遍历 ELF 头（e_type、e_machine、e_entry、
  e_flags）、程序头（PT_LOAD、PT_DYNAMIC、PT_INTERP、PT_GNU_STACK、
  PT_GNU_RELRO、PT_GNU_EH_FRAME）、节头（.text、.data、.bss、.dynamic、.got、
  .plt、.init_array、.fini_array、.symtab / .dynsym）、动态节（DT_NEEDED 导入、
  DT_RPATH / DT_RUNPATH、DT_BIND_NOW）、入口点放置异常、GNU 安全缓解标志，以及
  .init_array / .fini_array 前置初始化函数指针。通过 `PythonExecTool(lief)` 在
  分析沙箱内运行——绝不在主机上执行。将 `fact` indicator 写入 evidence chain 的
  `headers`、`imports` 和 `sections` bucket。适用于 ELF 样本（x86_64、ARM、
  AArch64、MIPS、RISC-V）、共享库（.so）、内核模块（.ko），以及任何 Linux /
  Android / 嵌入式恶意软件的 FR-04 结构解析请求。
license: Apache-2.0
compatibility: binary_analysis FR-04 · IR-09 · schema_version 1.0.0
allowed-tools: PythonExecTool BashTool EvidenceChainTool
metadata:
  id: Gap-05
  batch: C10
  adr: ADR-05, ADR-13
  fr: FR-04
  ir: IR-09
  stability: stable
---

# Analyzing ELF Structure（Gap-05）

> `skills/` 中已有一个覆盖面较宽的 ELF 专项技能
> `analyzing-linux-elf-malware`（最初自上游拷贝），覆盖动态追踪
> （strace / ltrace）、GDB 调试、Ghidra 反编译、UPX 解包和字符串 IOC 提取——
> 这些表面属于 FR-05、FR-06 和 FR-07，而非 FR-04。本技能填补结构解析缺口，使
> FR-04 验收标准"对 ELF 文件，系统提供对等的结构解析能力"（AC-16）与 IR-09
> "对 ELF / Mach-O 的结构解析深度必须与 PE 对等"得以满足，通过与 Gap-01
>（`analyzing-macho-structure`）和 Gap-02（`pe-structural-anomaly-checklist`）
> 严格对等的范围限定、evidence-chain 感知的工作流实现。

## 何时使用

- 样本的 `file_meta` bucket 中有 `tag: elf_detected`（由 FR-01
  `FileIdentifyTool` 写入）。
- 在 FR-05（熵）、FR-06（字符串）或 FR-07（反编译）运行之前，需要提取 ELF 头、
  程序头、节头、动态导入和 GNU 缓解标志。
- 调查共享库（`.so`）、内核模块（`.ko`），或包含多架构切片的胖 Android `.so`
  （通过 ABI split 机制嵌入 ARM 和 x86 切片）。
- Linux / Android 事件响应需要结构指纹（入口点放置、PT_GNU_STACK、DT_RPATH）
  用于归因。

**不要用于** ELF *动态追踪*或*代码*逆向工程——那属于 FR-07 via
`analyzing-linux-elf-malware`（已从 FR-04 重路由；拥有 strace / Ghidra / UPX
表面）。不要用于字符串 / IOC 提取（FR-06 via
`extracting-iocs-from-malware-samples`）。不要用于运行时行为分析（FR-17 via
`two-phase-behavior-chain-reconstruction`）。

## 前提条件

- 分析沙箱镜像中提供 `lief`（ELF 解析器）。优先于 `pyelftools`，原因是 `lief`
  通过与 Gap-01 / Gap-02 中 PE 和 Mach-O 解析器相同的统一接口暴露节、段和动态
  符号表。
- 通过 `BashTool` 使用 `readelf` / `objdump`（GNU binutils；标准 Linux 沙箱
  镜像中存在），作为交叉验证（尽力而为）；若缺失，记录 `tool_missing` gap fact。
- 样本已由 `upload_sample_to_sandbox`（C6）上传至 `/workspace/<analysis_id>/`。
  **绝不在主机上读取原始字节** — ADR-05 / NFR-04 要求仅限沙箱执行。
- 追加任何 indicator 之前，读取 `binary-analysis-evidence-chain-protocol`
  （Proto-02），了解 bucket 路由 + `kind: fact` 契约。

## 工作流

### Step 1：确认 ELF magic，分类 e_type / e_machine

每个 ELF 文件以 4 字节 magic（`\x7fELF`）开头，ELF 头随后声明 ABI 类别（32/64
位）、字节序、OS/ABI、对象类型（`ET_EXEC`、`ET_DYN`、`ET_REL`、`ET_CORE`）、
目标机器（`EM_X86_64`、`EM_ARM`、`EM_AARCH64`、`EM_MIPS`、`EM_RISCV`）和
虚拟入口点地址。

```python
# 通过 PythonExecTool 在沙箱内运行。
import lief

sample = "/workspace/{analysis_id}/sample.elf"
elf = lief.ELF.parse(sample)
if elf is None:
    raise RuntimeError("lief: not a valid ELF file")

hdr = elf.header
print(
    f"e_type={hdr.file_type.name} "
    f"e_machine={hdr.machine_type.name} "
    f"e_class={'ELF64' if elf.type == lief.ELF.ELF_CLASS.CLASS64 else 'ELF32'} "
    f"e_entry=0x{hdr.entrypoint:x} "
    f"e_flags=0x{hdr.processor_flag:x} "
    f"stripped={elf.get_section('.symtab') is None}"
)
```

**应发出的 indicator**（bucket: `headers`，`kind: fact`，`tool: "lief"`）：

| `indicator_type` | 发出时机 | `severity` |
|-----------------|----------|-----------|
| `elf_header` | 始终 | `INFO` |
| `elf_stripped` | `.symtab` 缺失 | `LOW` |
| `elf_shared_object_pie` | `e_type = ET_DYN` 且为可执行文件（PIE） | `INFO` |
| `elf_et_rel_fragment` | `e_type = ET_REL` — 可重定位，无段 | `MEDIUM` |

### Step 2：程序头（段）→ `headers` bucket

程序头描述*运行时*布局：哪些文件范围映射到内存（PT_LOAD）、`ld.so` 在哪里
（PT_INTERP）、动态链接器数据位于何处（PT_DYNAMIC），以及请求了哪些 GNU 安全策略
（PT_GNU_STACK、PT_GNU_RELRO）。

```python
for seg in elf.segments:
    print(
        f"type={seg.type.name} "
        f"vaddr=0x{seg.virtual_address:x} "
        f"vsize=0x{seg.virtual_size:x} "
        f"fsize=0x{seg.physical_size:x} "
        f"flags={seg.flags}"
    )
```

**与 FR-04 AC-3 / AC-13 对 PE / Mach-O 标记的同类异常，在 ELF 中同步复现**：

| `indicator_type` | 触发条件 | `severity` |
|-----------------|----------|-----------|
| `elf_wx_load_segment` | 任何 `PT_LOAD` 同时具有 `PF_W` 和 `PF_X` 标志 | `HIGH` |
| `elf_segment_size_mismatch` | `p_memsz > p_filesz * 4` — 运行时零填充异常（加壳解包缓冲区） | `MEDIUM` |
| `elf_no_pt_gnu_stack` | `PT_GNU_STACK` 段缺失（栈隐式可执行） | `MEDIUM` |
| `elf_executable_stack` | `PT_GNU_STACK` 存在但设置了 `PF_X` | `HIGH` |
| `elf_no_pt_gnu_relro` | `PT_GNU_RELRO` 缺失（重定位后 GOT/PLT 不是只读） | `LOW` |
| `elf_missing_pt_interp` | `e_type = ET_EXEC` 但无 `PT_INTERP` — 静态链接 | `INFO` |

> **关于 `elf_no_pt_gnu_stack` 的说明：** Go、musl-libc 等合法静态编译二进制
> 可能确实省略该段。与 `elf_missing_pt_interp` 交叉核对；若两者均存在，说明是
> 静态链接，缺失在意料之中。

### Step 3：节头 → `sections` bucket

节头描述*链接时*视图：命名区域（.text、.data、.rodata、.bss、.got、.plt、
.dynamic、.init_array、.fini_array）。恶意软件通常去除或重命名节——节头表本身
缺失也是一个信号。

```python
if not elf.sections:
    # 节表已去除——合法 ELF，但降低静态分析能力。
    print("WARN: no section headers (section table stripped)")
else:
    for sec in elf.sections:
        print(
            f"name={sec.name!r} "
            f"type={sec.type.name} "
            f"flags={sec.flags} "
            f"vaddr=0x{sec.virtual_address:x} "
            f"size={sec.size} "
            f"offset=0x{sec.offset:x}"
        )
```

**应发出的异常**（bucket: `sections`，`kind: fact`，`tool: "lief"`）：

| `indicator_type` | 触发条件 | `severity` |
|-----------------|----------|-----------|
| `elf_section_table_stripped` | `len(elf.sections) == 0` | `MEDIUM` |
| `elf_section` | 每节一条 — 目录 | `INFO` |
| `elf_wx_section` | 节同时具有 `SHF_WRITE` 和 `SHF_EXECINSTR` 标志 | `HIGH` |
| `elf_section_size_mismatch` | `sh_size` 为零但 `SHF_ALLOC` 已设置（空洞节） | `MEDIUM` |
| `elf_nonstandard_section` | 节名不在已知集合中（`.text`、`.data`、`.bss`、`.rodata`、`.got`、`.got.plt`、`.plt`、`.plt.got`、`.plt.sec`、`.dynamic`、`.dynstr`、`.dynsym`、`.symtab`、`.strtab`、`.shstrtab`、`.init`、`.fini`、`.init_array`、`.fini_array`、`.rela.*`、`.rel.*`、`.note.*`、`.eh_frame`、`.eh_frame_hdr`、`.debug_*`、`.tdata`、`.tbss`、`.interp`） | `LOW` |
| `elf_section_high_entropy` | 节熵 ≥ 7.2 | `MEDIUM` *（FR-05 种子）* |

### Step 4：动态节 → `imports` bucket

`.dynamic` 节是 PE 导入目录和 Mach-O `LC_LOAD_DYLIB` 列表的 ELF 对应物。
`DT_NEEDED` 条目枚举二进制文件向运行时链接器请求的每个共享库。`DT_RPATH` /
`DT_RUNPATH` 指定额外的库搜索路径——类似于 Mach-O `LC_RPATH` 异常的注入面。

```python
dyn = elf.get_section(".dynamic")
if dyn is not None:
    for entry in elf.dynamic_entries:
        print(f"tag={entry.tag.name} value={entry.value:#x}")
        if entry.tag in (lief.ELF.DYNAMIC_TAGS.NEEDED,
                         lief.ELF.DYNAMIC_TAGS.RPATH,
                         lief.ELF.DYNAMIC_TAGS.RUNPATH):
            print(f"  -> {entry.name!r}")
```

能力分组 — 每种能力发出一条聚合 `fact`，`data.libraries = [...]`（bucket:
`imports`）：

| 能力 | 典型库 / 符号模式 |
|------|------------------|
| `network` | `libcurl.so.*`、`libssl.so.*`、`socket`、`connect`、`sendto`、`recvfrom` |
| `crypto` | `libcrypto.so.*`、`libssl.so.*`、`EVP_*`、`AES_*`、`SHA256_*` |
| `process_manipulation` | `ptrace`、`fork`、`execve`、`clone`、`prctl`、`kill` |
| `dynamic_loading` | `libdl.so.*`、`dlopen`、`dlsym`、`dlmopen` |
| `persistence` | 提示 `crontab`、`systemd`、`ld.so.preload`、`init.d` 的字符串（延迟到 FR-06；此处仅标注该表面） |

同时发出 `indicator_type: elf_import_count`（fact，INFO）——若 `DT_NEEDED` 数
异常低（< 2 个库），是静态链接 / 去除 / 加壳的信号，应从 FR-05 交叉引用。

**异常**（bucket: `imports`）：

| `indicator_type` | 触发条件 | `severity` |
|-----------------|----------|-----------|
| `elf_rpath_anomaly` | `DT_RPATH` 或 `DT_RUNPATH` 包含可写或相对路径（`.`、`$ORIGIN/..`、`/tmp`、`/var/tmp`）——运行时库劫持面 | `HIGH` |
| `elf_missing_bind_now` | `DT_BIND_NOW` 和 `DF_BIND_NOW` 均未设置，且 `PT_GNU_RELRO` 缺失——懒绑定 + 可写 GOT | `MEDIUM` |
| `elf_no_dynamic_section` | 静态链接二进制（无 `.dynamic`）；与 `elf_missing_pt_interp` 共存可确认静态链接 | `INFO` |

### Step 5：入口点放置（FR-04 AC-3）

ELF 入口点（`e_entry`）是映射到某个 `PT_LOAD` 段的虚拟地址。健康的可执行文件
入口点落在覆盖 `.text` 节的非可写、可执行 `PT_LOAD` 段内。

```python
ep = hdr.entrypoint
ep_segment = None
ep_section = None

for seg in elf.segments:
    if seg.type == lief.ELF.SEGMENT_TYPES.LOAD:
        seg_start = seg.virtual_address
        seg_end = seg_start + seg.virtual_size
        if seg_start <= ep < seg_end:
            ep_segment = seg
            break

if elf.sections and ep_segment is not None:
    for sec in elf.sections:
        sec_start = sec.virtual_address
        sec_end = sec_start + sec.size
        if sec.size > 0 and sec_start <= ep < sec_end:
            ep_section = sec
            break

print(f"ep=0x{ep:x} segment={ep_segment} section={ep_section and ep_section.name!r}")
```

| `indicator_type` | 触发条件 | `severity` |
|-----------------|----------|-----------|
| `elf_entry_point_zero` | `ET_EXEC` 上 `e_entry == 0` | `HIGH` |
| `elf_entry_point_oob` | `e_entry` 不落在任何 `PT_LOAD` 内 | `HIGH` |
| `elf_entry_point_wx_segment` | 所属 `PT_LOAD` 同时具有 `PF_W` 和 `PF_X` | `HIGH` |
| `elf_entry_point_odd_section` | 所属节不是 `.text` / `.init` / `_start` | `MEDIUM` |

Bucket: `headers`。Payload: `{"ep_va": 0x..., "segment_flags": "RX",
"section": "<name or null>"}`。

FR-07 在构建反编译优先队列时**必须**消费 `elf_entry_point_*` fact（ADR-06 /
IR-05）。

### Step 6：.init_array / .fini_array — 前置初始化函数

ELF 中 PE TLS Callback 和 Mach-O `__mod_init_func` 的对应物是 `.init_array`
节：一个函数指针数组，由动态链接器在 `main` *之前*调用。此处的代码在名义入口点
之前无声执行，是加壳 / 投放程序的经典隐藏位置（FR-04 AC-8）。

```python
for sec_name in (".init_array", ".fini_array", ".init", ".fini"):
    sec = elf.get_section(sec_name)
    if sec is None:
        continue
    pointer_size = 8 if elf.type == lief.ELF.ELF_CLASS.CLASS64 else 4
    count = sec.size // pointer_size if pointer_size else 0
    print(f"{sec_name}: {count} pointer(s), size={sec.size}")
```

每个指针槽（而非每字节）发出一条
`fact, severity: MEDIUM, indicator_type: elf_init_array_entry`，带
`data.section = ".init_array"` 和 `data.slot_index = N`。FR-07 **必须**消费
这些 fact 以建立反编译优先级（IR-05 / ADR-06）。

### Step 7：用 `readelf` 交叉验证（尽力而为）

若 GNU binutils 在沙箱中可用，通过 `BashTool` 交叉验证可增强 `lief` 解析的
可信度。结果标注 `evidence_refs` 指向 `lief` 输出；若 `readelf` 不可用，记录
`tool_missing` gap fact。

```bash
readelf -h /workspace/{analysis_id}/sample.elf      # ELF 头
readelf -l /workspace/{analysis_id}/sample.elf      # 程序头
readelf -S /workspace/{analysis_id}/sample.elf      # 节头
readelf -d /workspace/{analysis_id}/sample.elf      # 动态节
readelf -s /workspace/{analysis_id}/sample.elf      # 符号表
```

## 关键术语

| 术语 | 定义 |
|------|------|
| **ELF 头** | 文件前 64 字节（ELF64）；声明 magic、类别（32/64 位）、字节序、OS/ABI、对象类型（`ET_EXEC` / `ET_DYN` / `ET_REL` / `ET_CORE`）、机器类型、入口点 VA，以及段表和节表的偏移。 |
| **程序头（段）** | 告知 `ld.so` 如何将文件映射到内存的运行时描述符 — `PT_LOAD`（可映射）、`PT_DYNAMIC`（动态链接器数据）、`PT_INTERP`（解释器路径）、`PT_GNU_STACK`（栈可执行位）、`PT_GNU_RELRO`（GOT/PLT 加固）。 |
| **节头** | 命名文件区域的链接时描述符（`.text`、`.data`、`.bss`、`.got`、`.plt` 等）。链接后可去除以减小体积或妨碍分析。 |
| **动态节（`.dynamic`）** | 指导运行时链接器的标签-值条目数组：`DT_NEEDED`（库名）、`DT_RPATH` / `DT_RUNPATH`（库搜索路径）、`DT_BIND_NOW` / `DF_BIND_NOW`（急切符号解析）、`DT_DEBUG`。 |
| **GOT / PLT** | 全局偏移表和过程链接表；ELF 懒绑定结构。若无 `RELRO` + `BIND_NOW`，GOT 在运行时可写——ret2plt / GOT 覆写攻击的经典目标。 |
| **PT_GNU_STACK** | 设置进程栈可执行权限的可选程序头。缺失表示栈可执行（历史默认）——旧工具链或故意去除的信号。 |
| **PT_GNU_RELRO** | 标记重定位后设为只读的内存范围；保护 GOT 等敏感表。结合 `BIND_NOW` 构成"Full RELRO"。 |
| **`.init_array` / `.fini_array`** | 存放由 `ld.so` 在 `main` 前/后调用的函数指针数组的节；PE TLS Callback 和 Mach-O `__mod_init_func` 的 ELF 对应物。 |
| **去除（Stripped）** | 移除了 `.symtab` 节的 ELF 二进制。`.dynsym`（导出/导入动态符号）可能仍存在；`.symtab`（所有本地符号 + 调试名称）可选，生产版本通常去除。 |

## 工具与系统

- **lief** — 跨平台二进制解析器（Python API），通过统一接口暴露 ELF、PE 和
  Mach-O；分析沙箱内的首选工具。
- **readelf** — GNU binutils ELF 检查器（`-h`、`-l`、`-S`、`-d`、`-s`、
  `-r`）；可用时的尽力而为交叉验证。
- **objdump** — GNU 反汇编器 / 元数据转储工具；当 `readelf` 输出不足时，用于
  `.plt` / `.got` 检查。
- **pyelftools** — 纯 Python ELF 解析器；`lief` 在畸形文件上抛错时的回退。
  暴露 `ELFFile`、`iter_segments()`、`iter_sections()` 和
  `get_section_by_name()`。

## 常见场景

### 场景：对云虚拟机 `/usr/local/bin/` 中投放的 ARM64 ELF 进行分流

**背景**：EDR 告警触发于某生产 ARM64 Ubuntu 22.04 云实例
`/usr/local/bin/sshd_cfg` 中出现的新二进制文件。分析师将二进制路径提交至
binary_analysis 后端，在启动隔离执行环境之前先进行结构分流。

**方法**：
1. FR-01 `FileIdentifyTool` 将 `tag: elf_detected` + `e_machine: EM_AARCH64`
   写入 `file_meta`；FR-02 启发式分流未记录强家族或加壳路由。
2. FR-04 激活本技能。解析 ELF 头：`ET_DYN`、`EM_AARCH64`，已去除符号表
   （`.symtab` 缺失）。发出 `elf_header`（INFO）+ `elf_stripped`（LOW）。
3. 程序头：`PT_GNU_STACK` 缺失 → `elf_no_pt_gnu_stack`（MEDIUM）；
   `PT_GNU_RELRO` 缺失 → `elf_no_pt_gnu_relro`（LOW）。一个 `PT_LOAD` 带有
   `PF_W | PF_X` → `elf_wx_load_segment`（HIGH）。
4. 节头：仅 3 节（节表未完全去除，但异常稀疏）。无 `.init_array`。一节命名为
   `.obb` — 发出 `elf_nonstandard_section`（LOW）。
5. 动态节：`DT_NEEDED: libpthread.so.0`、`libdl.so.2` — 发出
   `capability: dynamic_loading`；导入数 = 2 → `elf_import_count`（INFO，低
   导入数异常提示）。`DT_RPATH` = `/tmp/.libcache` →
   `elf_rpath_anomaly`（HIGH）。
6. 入口点：`e_entry` 落在 `PF_W | PF_X` 段内 →
   `elf_entry_point_wx_segment`（HIGH）。FR-07 随后在反编译优先队列中最先调度
   该地址。
7. FR-05 确认全局熵 7.4 — 可能已加壳或加密。FR-08 基于 `dynamic_loading` 能力
   + `elf_rpath_anomaly` + 高熵推断 `cryptominer or backdoor`，置信度 MEDIUM。

**注意事项**：
- 将 PIE 可执行文件（`ET_DYN`）误判为共享库 — 检查 `e_entry` 是否非零；共享库
  通常 `e_entry = 0`。
- 在沙箱外对恶意软件运行 `readelf` 或 `ldd`；`ldd` 内部会执行该二进制，可能
  触发 payload 执行（`analyzing-linux-elf-malware` 中亦有记录）。
- 将 `.symtab` 缺失视为刻意加固的证明——大多数发布版本均去除符号表；只有结合
  其他信号（`elf_wx_load_segment`、低导入数、高熵）才提升严重级别。

## 输出格式

本技能不自行产出报告；所有发现经 Proto-02 写入共享 evidence chain。成功运行的
可见结果如下：

- 每个样本一条 `elf_header` fact，位于 `headers`。
- N 条 `elf_segment` fact，位于 `headers`，加上触发的异常标签
  （`elf_wx_load_segment` / `elf_segment_size_mismatch` / `elf_no_pt_gnu_stack`
  / `elf_executable_stack` / `elf_no_pt_gnu_relro`）。
- 一条 `elf_entry_point_*` fact，位于 `headers`。
- M 条 `elf_section` fact，位于 `sections`，加上适用时的
  `elf_wx_section` / `elf_section_size_mismatch` / `elf_nonstandard_section` /
  `elf_section_high_entropy` 异常。
- K 条 `elf_capability` 聚合 fact，位于 `imports`，加上 `elf_import_count`
  和原始 `elf_needed_library` fact。
- 零或多条 `elf_init_array_entry` fact，位于 `headers`，供 FR-07 优先级排序
  消费。
- 动态节有异常时，`elf_rpath_anomaly` 和/或 `elf_missing_bind_now` fact，位于
  `imports`。

若 `lief.ELF.parse` 中途失败（畸形节表、文件截断），在 `headers` 中发出一条
`fact, severity: HIGH, indicator_type: malformed_structure`，并按 Proto-01
降级纪律在 `analysis_coverage` 中记录降级——绝不向 Agent 循环抛出异常。
