# V93K Test Method API 参考

## 1 Test Method 概述

V93000 的 Test Method 是用 C++ 编写的测试类，每个 Test Method 对应一个具体的测试项（如功能测试、直流参数测试等）。Test Method 通过调用 SmarTest 提供的测试 API 来操作测试机硬件资源，执行测试并判定结果。

Test Method 文件的典型结构：

```cpp
#include "V93kTestAPI.h"

class MyTest : public TestClass {
public:
    void setup() {
        // 测试参数设置（程序加载时执行一次）
    }
    void execute() {
        // 测试执行体（每颗芯片都会执行）
    }
};
REGISTER_TESTCLASS("my_test", MyTest);
```

## 2 FunctionalTest API（功能测试）

功能测试是最常用的测试类型，执行 STIL 中定义的测试向量，比对输出与期望值。

### 2.1 基本用法

```cpp
#include "V93kTestAPI.h"

class FunctionalTestDemo : public TestClass {
public:
    void execute() {
        FunctionalTest ft;
        ft.pinList("@");            // "@" 表示使用器件定义文件中的全部引脚
        ft.execute();               // 执行功能测试

        if (ft.hasPassed()) {
            // 测试通过
        } else {
            // 测试失败
            int fail_cycle = ft.getFirstFailCycle();
            std::string fail_pin = ft.getFirstFailPin();
        }
    }
};
```

### 2.2 常用方法

| 方法 | 说明 | 示例 |
|------|------|------|
| `pinList(const char*)` | 指定参与测试的引脚 | `ft.pinList("@")` 全部引脚；`ft.pinList("clk,data_in")` 指定引脚 |
| `execute()` | 执行测试 | `ft.execute()` |
| `hasPassed()` | 判断是否通过 | `if (ft.hasPassed())` |
| `getFirstFailCycle()` | 获取第一个失败的周期号 | `int cycle = ft.getFirstFailCycle()` |
| `getFirstFailPin()` | 获取第一个失败的引脚名 | `string pin = ft.getFirstFailPin()` |
| `getFailCount()` | 获取失败总数 | `int cnt = ft.getFailCount()` |
| `setPatternName(const char*)` | 指定要执行的 Pattern 名 | `ft.setPatternName("func_pat")` |
| `setWaveformTable(const char*)` | 指定使用的 WaveformTable | `ft.setWaveformTable("basic_wft")` |
| `setStartCycle(int)` | 设置起始周期 | `ft.setStartCycle(0)` |
| `setStopCycle(int)` | 设置停止周期 | `ft.setStopCycle(1000)` |

### 2.3 PinGroup 用法

```cpp
// 使用信号组
FunctionalTest ft;
ft.pinList("_pi");              // 只测输入引脚组
ft.execute();

// 使用多个引脚
ft.pinList("clk,data_in");     // 逗号分隔

// 排除某些引脚
ft.pinList("@ - vdd - gnd");   // 全部引脚去掉电源和地
```

## 3 DC_Test API（直流参数测试）

直流参数测试用于测量器件的直流电气特性，如开路/短路测试（Continuity）、漏电流（Leakage）、输出驱动电流等。

### 3.1 开路/短路测试（Continuity Test）

```cpp
class ContinuityTest : public TestClass {
public:
    void execute() {
        DC_Test dc;
        dc.pinList("@");

        // 设置驱动模式：Force Current, Measure Voltage
        dc.forceMode(DC_Test::FORCE_CURRENT);
        dc.forceValue(100e-6);          // 强制 100μA 电流
        dc.clampVoltage(2.0);           // 钳位电压 2V
        dc.measureMode(DC_Test::MEASURE_VOLTAGE);

        dc.execute();

        float voltage = dc.getMeasuredValue();
        // 正常二极管压降约 0.6-0.7V，若 < 0.1V 则短路，> 1.5V 则开路
        if (voltage < 0.1 || voltage > 1.5) {
            // Continuity Fail
        }
    }
};
```

### 3.2 漏电流测试（Leakage Test）

```cpp
class LeakageTest : public TestClass {
public:
    void execute() {
        DC_Test dc;
        dc.pinList("data_out");

        // Force Voltage, Measure Current
        dc.forceMode(DC_Test::FORCE_VOLTAGE);
        dc.forceValue(0.0);             // 强制 0V
        dc.clampCurrent(1e-3);          // 电流钳制 1mA
        dc.measureMode(DC_Test::MEASURE_CURRENT);

        dc.execute();

        float current = dc.getMeasuredValue();
        // 漏电流应 < 规格值（如 1μA）
        if (std::abs(current) > 1e-6) {
            // Leakage Fail
        }
    }
};
```

### 3.3 DC_Test 常用方法

| 方法 | 说明 |
|------|------|
| `pinList(const char*)` | 指定测试引脚 |
| `forceMode(mode)` | 设置强制模式：`FORCE_VOLTAGE` 或 `FORCE_CURRENT` |
| `forceValue(float)` | 设置强制值（电压 V 或电流 A） |
| `clampVoltage(float)` | 设置电压钳位（保护） |
| `clampCurrent(float)` | 设置电流钳位（保护） |
| `measureMode(mode)` | 设置测量模式：`MEASURE_VOLTAGE` 或 `MEASURE_CURRENT` |
| `execute()` | 执行测试 |
| `getMeasuredValue()` | 获取测量结果 |
| `hasPassed()` | 判断是否通过 |
| `setHighLimit(float)` | 设置上限 |
| `setLowLimit(float)` | 设置下限 |

## 4 Analog_Test API（模拟测试）

模拟测试用于混合信号器件的波形发生与采集分析。

### 4.1 任意波形发生器（AWG）

```cpp
class AWGDemo : public TestClass {
public:
    void execute() {
        Analog_Test analog;

        // 配置 AWG 输出
        analog.awgChannel("awg_ch0");       // 指定 AWG 通道
        analog.awgWaveform(Analog_Test::SINE);  // 正弦波
        analog.awgFrequency(1e6);           // 1MHz
        analog.awgAmplitude(0.5);           // 0.5V 幅度
        analog.awgOffset(0.0);              // 0V 偏置
        analog.awgStart();                  // 开始输出
    }
};
```

### 4.2 数字采样器（Digitizer）

```cpp
class DigitizerDemo : public TestClass {
public:
    void execute() {
        Analog_Test analog;

        // 配置 Digitizer 采集
        analog.digitizerChannel("dig_ch0");
        analog.digitizerSampleRate(100e6);   // 100MHz 采样率
        analog.digitizerSamples(1024);       // 采集 1024 个点
        analog.digitizerTrigger(Analog_Test::SOFTWARE_TRIGGER);
        analog.digitizerStart();

        // 获取采集数据
        std::vector<float> data = analog.digitizerGetData();

        // FFT 分析
        float thd = analog.analyzeTHD(data);  // 总谐波失真
        float snr = analog.analyzeSNR(data);  // 信噪比
    }
};
```

## 5 T_Test API（时间测量）

时间测量用于测试信号的时序特性，如频率、周期、传播延时等。

### 5.1 频率测量

```cpp
class FreqTest : public TestClass {
public:
    void execute() {
        T_Test ttest;
        ttest.pinList("clk_out");

        ttest.measureMode(T_Test::FREQUENCY);
        ttest.gateTime(1e-3);              // 测量门时间 1ms
        ttest.execute();

        float freq = ttest.getMeasuredValue();
        // 期望频率 100MHz ± 1%
        if (freq < 99e6 || freq > 101e6) {
            // Frequency Fail
        }
    }
};
```

### 5.2 传播延时测量

```cpp
class PropDelayTest : public TestClass {
public:
    void execute() {
        T_Test ttest;
        ttest.pinList("data_out");

        ttest.measureMode(T_Test::PROPAGATION_DELAY);
        ttest.referencePin("clk");         // 参考信号
        ttest.edgeType(T_Test::RISING);    // 上升沿触发
        ttest.execute();

        float delay = ttest.getMeasuredValue();  // 延时值（秒）
        // 期望延时 < 10ns
    }
};
```

## 6 PMU API（参数测量单元）

PMU（Parametric Measurement Unit）用于精确的直流参数测量，精度高于 DC_Test。

```cpp
class PMUTest : public TestClass {
public:
    void execute() {
        PMU pmu;
        pmu.pinList("data_in");

        pmu.forceMode(PMU::FORCE_VOLTAGE);
        pmu.forceValue(1.8);
        pmu.measureMode(PMU::MEASURE_CURRENT);
        pmu.execute();

        float current = pmu.getMeasuredValue();
        if (pmu.hasPassed()) {
            // PMU 测试通过
        }
    }
};
```

## 7 测试流程控制

### 7.1 测试分类（Test Suite）

```cpp
// 在 Test Method 中访问测试结果统计
void execute() {
    FunctionalTest ft;
    ft.pinList("@");
    ft.execute();

    // 设置 Bin Code
    if (ft.hasPassed()) {
        setBin(1);      // Bin 1: Pass
    } else {
        setBin(10);     // Bin 10: Functional Fail
    }
}
```

### 7.2 Datalog 输出

```cpp
// 将测试结果写入 Dlog
void execute() {
    DC_Test dc;
    dc.pinList("vdd");
    // ... 设置参数 ...
    dc.execute();

    float value = dc.getMeasuredValue();
    datalog("vdd_current", value);    // 写入 Dlog，便于后续分析
}
```

### 7.3 条件执行

```cpp
// 根据前一步测试结果决定是否执行
void execute() {
    FunctionalTest ft;
    ft.pinList("@");
    ft.execute();

    if (ft.hasPassed()) {
        // 功能 Pass，继续做速度测试
        FunctionalTest speed_ft;
        speed_ft.setWaveformTable("fast_wft");
        speed_ft.pinList("@");
        speed_ft.execute();
    }
    // 功能 Fail，跳过速度测试
}
```

## 8 Test Method 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `execute()` 返回但无结果 | 未调用 `hasPassed()` 或未设置 Datalog | 确保测试后有结果判定和输出 |
| 编译报 `undefined reference` | 缺少库链接或头文件 | 检查 `#include` 和项目链接设置 |
| `pinList` 无引脚参与 | 引脚名拼写错误或未在 Signals 中定义 | 核对 STIL Signals 块中的引脚名 |
| 测试时间过长 | Pattern 过多或未做 Multi-Site | 优化 Pattern 数量，启用并行测试 |
| 测量值不稳定 | 未做平均或测量次数太少 | 增加 `setAverageCount(N)` 或多次测量取均值 |
