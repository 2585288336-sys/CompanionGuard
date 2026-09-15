# CompanionGuard 实验执行规则 / Experiment Execution

## 1. 每个 case 都从干净上下文开始

以下任意变化都表示进入一个新的独立 case，应在被测产品中新建对话或清空上下文：

- C0 → C1 → C2；
- criterion 改变，例如 DS-01 → FD-01；
- scenario 改变，例如 MR-01 → MR-02；
- run 改变，例如 Run 1 → Run 2；
- product 改变。

同一个 case 内的后续轮次必须保留在同一产品对话中。

## 2. C0 / C1 / C2 的关系

C0、C1、C2 是三个独立实验条件，不是同一场对话中的三个阶段。

### C0｜集中式基线

1. L1–L4 合并为一条用户消息；
2. 记录 A4（Pre-trigger）；
3. 发送 canonical L5；
4. 记录 A5（Post-trigger）。

### C1｜集中式压力

1. 在一个全新的产品对话中发送与 C0 相同的 L1–L4；
2. 记录 A4；
3. 发送冻结的 `pressure_variant.L5`；
4. 记录 A5。

C1 不是“C0 的后续 L5”，而是另一条独立 case。

### C2｜顺序多轮

在另一个全新的产品对话中依次发送：

`L1 → A1 → L2 → A2 → L3 → A3 → L4 → A4 → L5 → A5`

C2 的 L5 是 canonical L5，不是 Pressure L5。C2 的核心变化是 L1–L4 从集中表达改为顺序累积。

## 3. 专项结构

- MR：`R1 → A_R1 → R2 → A_R2`，两轮属于同一个 case；不同 MR scenario 重新开对话。
- MC / PC：每个 single-turn scenario 是一个独立 case，应使用干净上下文。
- HR-02：仍遵守 C0/C1/C2；同一 case 内保持连续上下文。

## 4. 截图

截图是支持性实验凭证，不是保存文本回复的前置条件。能复制文本时，以逐字复制的模型回复作为 Judge 的主要输入；截图按 response turn 自动关联。

## 5. SMOKE / CALIBRATION / FORMAL

SMOKE 与 CALIBRATION 可以与 FORMAL 保存在同一项目目录中，但必须通过 `phase` 区分。正式结果与正式综合报告只使用 `phase == FORMAL`。为了最清晰的数据治理，推荐把 UI smoke test 单独建立成一个 Test Project。
