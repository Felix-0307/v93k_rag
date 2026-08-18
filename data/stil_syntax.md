# STIL 测试语言语法详解

## 1 STIL 概述

STIL（Standard Test Interface Language，IEEE 1450）是描述半导体测试信息的标准语言。在 V93000 中，STIL 文件用于定义被测器件（DUT）的引脚、信号电平、时序、测试向量（Pattern）等信息，是测试程序的核心数据文件。

STIL 文件的扩展名通常为 `.stil` 或 `.spf`（Signal Protocol File），本质上是纯文本，可用任意文本编辑器编写。

## 2 STIL 文件基本结构

一个完整的 STIL 文件由若干块（Block）组成，每个块以块名开头、分号结尾。基本框架：

```stil
STIL 1.0;

SignalGroups {
    _pi = 'clk + data_in';
    _po = 'data_out';
}

Signals {
    clk      In;
    data_in  In;
    data_out Out;
}

SignalGroups {
    _all = 'clk + data_in + data_out';
}

Timing {
    WaveformTable basic_wft {
        Period '10ns';
        Waveforms {
            _pi  { 01 { '0ns' D; } }
            _po  { H  { '7ns' C; } }
        }
    }
}

PatternBurst {
    main_burst {
        PatList { functional_pat; }
    }
}
```

## 3 Signals 块

定义器件的所有引脚及其方向。

```stil
Signals {
    // 格式：信号名  方向;
    clk       In;       // 输入引脚
    data_in   In;       // 输入引脚
    data_out  Out;      // 输出引脚
    vdd       Power;    // 电源引脚（V93K 中通常由 DPS 管理，此处仅为声明）
    gnd       Power;    // 地引脚
    bidir_io  InOut;    // 双向引脚
}
```

**方向关键字**：
- `In`：输入引脚（测试机驱动）
- `Out`：输出引脚（测试机采集比对）
- `InOut`：双向引脚
- `Power`：电源/地引脚
- `Supply`：电源引脚（部分 STIL 方言）

## 4 SignalGroups 块

将多个信号组合为一个组，方便后续批量引用。

```stil
SignalGroups {
    // 格式：组名 = '信号1 + 信号2 + ...';
    _pi   = 'clk + data_in + addr[0:7]';   // 全部输入
    _po   = 'data_out + status[0:3]';       // 全部输出
    _all  = '_pi + _po';                     // 全部信号

    // 位域展开：addr[0:7] 表示 addr0, addr1, ..., addr7
    addr  = 'addr[0:7]';                    // 8 位地址总线
}
```

**位域语法**：
- `name[MSB:LSB]`：展开为 nameMSB, name(MSB-1), ..., nameLSB
- 例如 `data[7:0]` → `data7, data6, ..., data0`

## 5 Levels 块（电平定义）

定义各引脚的逻辑电平阈值和驱动电压。

```stil
Levels {
    // 格式：信号/组  参数 = 值;

    // 输入引脚电平（测试机驱动给 DUT 的电平）
    _pi {
        Vil = '0.0V';      // 输入低电平阈值
        Vih = '1.8V';      // 输入高电平阈值
    }

    // 输出引脚电平（测试机判断 DUT 输出的阈值）
    _po {
        Vol = '0.4V';      // 输出低电平阈值（低于此值判为逻辑 0）
        Voh = '1.4V';      // 输出高电平阈值（高于此值判为逻辑 1）
    }
}
```

**关键参数说明**：
- `Vil`（V input low）：输入低电平电压，测试机驱动此电压表示逻辑 0
- `Vih`（V input high）：输入高电平电压，测试机驱动此电压表示逻辑 1
- `Vol`（V output low）：输出低电平阈值，DUT 输出低于此值判为逻辑 0
- `Voh`（V output high）：输出高电平阈值，DUT 输出高于此值判为逻辑 1
- `Vcl`：电流钳位电压（保护用）
- `Iil/Iih`：输入低/高电平电流（用于 Continuity 测试）

## 6 Timing 块（时序定义）

定义测试周期、波形格式和边沿时间。

### 6.1 WaveformTable

```stil
Timing {
    WaveformTable basic_wft {
        Period '10ns';          // 一个信号周期 = 10ns

        Waveforms {
            // 输入引脚组：NRZ 格式，驱动边沿在 0ns
            _pi {
                01 { '0ns' D; }   // 从 0→1：在 0ns 驱动为高
                10 { '0ns' D; }   // 从 1→0：在 0ns 驱动为低
                11 { '0ns' D; }   // 保持 1：在 0ns 驱动为高
                00 { '0ns' D; }   // 保持 0：在 0ns 驱动为低
            }

            // 输出引脚组：比较边沿在 7ns
            _po {
                H  { '7ns' C; }   // 高电平比较：在 7ns 采样，期望为 1
                L  { '7ns' C; }   // 低电平比较：在 7ns 采样，期望为 0
                X  { '7ns' X; }   // 不关心：在 7ns 不比较
            }
        }
    }
}
```

### 6.2 波形字符（WFC）含义

**输入引脚（D = Drive）**：
| WFC | 含义 | 说明 |
|-----|------|------|
| `01` | 从 0 变为 1 | 上升沿驱动 |
| `10` | 从 1 变为 0 | 下降沿驱动 |
| `00` | 保持 0 | 持续低电平 |
| `11` | 保持 1 | 持续高电平 |

**输出引脚（C = Compare）**：
| WFC | 含义 | 说明 |
|-----|------|------|
| `H` | 期望高电平 | 采样后与 Voh 比较 |
| `L` | 期望低电平 | 采样后与 Vol 比较 |
| `X` | 不关心 | 不做比较 |
| `M` | 高阻态比较 | 期望高阻 |

### 6.3 波形数据格式（Data Format）

| 格式 | 全称 | 行为 | 适用场景 |
|------|------|------|---------|
| NRZ | Non-Return to Zero | 信号在周期内保持电平不变 | 最常用，一般数字测试默认 |
| RZ | Return to Zero | 先驱动目标电平，再回到 0 | 需要脉冲信号时 |
| RO | Return to One | 先驱动目标电平，再回到 1 | 类似 RZ，回到高 |
| SBC | Surround By Complement | 先驱动补码，再驱动目标电平 | 增强信号边沿能量 |
| DNRZ | Delayed NRZ | 延迟后的 NRZ | 时序微调 |

### 6.4 多时序表

可以定义多个 WaveformTable，用于不同测试条件：

```stil
Timing {
    WaveformTable slow_test {
        Period '100ns';
        Waveforms { ... }
    }

    WaveformTable fast_test {
        Period '10ns';
        Waveforms { ... }
    }
}
```

## 7 PatternBurst / PatternExec（测试向量执行）

### 7.1 PatternBurst

定义一组要执行的测试向量文件：

```stil
PatternBurst {
    func_burst {
        PatList {
            scan_test;          // 对应 Pattern 块名
            memory_test;
        }
    }
}
```

### 7.2 PatternExec

定义执行环境（使用哪个 Timing 和 SignalGroups）：

```stil
PatternExec {
    func_exec {
        Timing  = basic_wft;
        SignalGroups = _all;
        PatternBurst = func_burst;
    }
}
```

## 8 Pattern 块（测试向量）

定义具体的测试向量序列，每个向量描述一个周期内所有引脚的状态。

```stil
Pattern functional_pat {
    // 声明使用的信号组
    _pi  = ScanIn;
    _po  = ScanOut;

    // Vector 标签（可选，用于调试定位）
    start_loop:
        V { _pi = 00000001; _po = XXXXXXX0; }  // Cycle 1
        V { _pi = 00000010; _po = XXXXXXX1; }  // Cycle 2
        V { _pi = 00000100; _po = XXXXXXX0; }  // Cycle 3

    // Call 指令：调用另一个 Pattern
    call memory_test;

    // Repeat 指令：重复若干周期
    repeat 100 {
        V { _pi = 00000000; _po = XXXXXXXX; }
    }

    // Stop 指令：在特定位置停止（用于调试）
    stop;
}
```

### 8.1 Vector 数据格式

`V { _pi = 01XZHLU; _po = 01XZ; }` 中各字符含义：

| 字符 | 含义 | 说明 |
|------|------|------|
| `0` | 驱动低电平 / 期望低电平 | 输入时为驱动，输出时为比较 |
| `1` | 驱动高电平 / 期望高电平 | 输入时为驱动，输出时为比较 |
| `X` | 不关心 | 不做比较（输出时） |
| `Z` | 高阻态 | 高阻驱动或高阻比较 |
| `H` | 期望高电平（显式） | 用于输出引脚 |
| `L` | 期望低电平（显式） | 用于输出引脚 |
| `U` | 未定义 | 通常不使用 |

### 8.2 Scan（扫描链）

V93K 支持 Scan Chain 测试，用 Scan 表达式简化大量移位向量：

```stil
Pattern scan_test {
    // Scan 声明
    ScanChain scan_chain_0 {
        ScanIn  = scan_in;
        ScanOut = scan_out;
        ScanMasterClock = tck;
    }

    // Scan 操作
    Scan {
        // Load：移入 scan 数据
        Load scan_chain_0 {
            1010_1100_0011_1111;
        }
        // Unload：移出 scan 数据并比对
        Unload scan_chain_0 {
            1010_1100_0011_1111;
        }
    }
}
```

## 9 Macro 定义（宏）

STIL 支持宏定义，用于复用常见的信号模式：

```stil
MacroDefs {
    // 定义一个复位宏
    reset_sequence {
        V { _pi = 10000000; _po = XXXXXXXX; }  // rst_n 拉低
        V { _pi = 10000000; _po = XXXXXXXX; }  // 保持一周期
        V { _pi = 00000000; _po = XXXXXXXX; }  // rst_n 释放
    }
}

Pattern functional_pat {
    // 调用宏
    Call reset_sequence;
    V { _pi = 00000001; _po = XXXXXXX0; }
    // ...
}
```

## 10 STIL 文件常见错误

| 错误 | 原因 | 修正 |
|------|------|------|
| `syntax error near '}'` | 缺少分号，STIL 每个声明必须以 `;` 结尾 | 检查最近的 `}` 后是否有 `;` |
| `undefined signal group` | 引用了未定义的信号组名 | 检查 SignalGroups 块中的拼写 |
| `period too small` | 周期值小于测试机硬件支持的最小值 | 增大 Period（PS1600 最小约 2ns） |
| `pattern width mismatch` | 向量中信号数量与 SignalGroups 定义不一致 | 确保向量中每个信号组的位宽与声明匹配 |
| `missing WaveformTable` | PatternExec 引用了不存在的 WaveformTable | 检查 Timing 块中的命名 |
