# Open Items（待确认/待办事项清单）

<!-- toc-depth: 3 -->

> 创建：2026-08-31。集中记录会话中提出的待确认/待办事项，防止丢失。
> 用户新提出的待记录事项：追加到"待办事项"表尾，编号顺延（0.9、0.10…）。
> 已完成的条目移至文末"已完成（归档）"表，不再与进行中事项混排（2026-09-01）。
> 关联：`questions_dfe.md` 为问题整理主文档（结论 + 依据与推导），本文件仅作事项追踪。

> **Agent 导航**：勿整文件逐行读入。按开头"目录"节的起止行号，用 read_file(offset=章节起始行, limit=...) 直接跳章节；行号对不上（文件被编辑过）时，先 grep '^#' 重算当前标题行号。每章先读"结论"节，需溯源再读"依据与推导"，不必读全章推导细节。

## 目录

> 行号最后更新：2026-09-24（含到第 3 级标题；行号随编辑漂移，改动后重跑本脚本）。

| 章节 | 起始行 | 结束行 |
|---|----|----|
| 待办事项（进行中） | 22 | 40 |
| 已完成（归档） | 41 | 55 |
| 已落盘记录索引（2026-08-31） | 56 | 67 |

## 待办事项（进行中）

| # | 事项 | 状态 | 详情/方向 | 提出 |
|---|------|------|-----------|------|
| 0.8 | cfg_midpoint_phase_os 偏置 / add_phase_offset_only 功能必要性 | 待问领导（用户认为不应存在） | 见 questions_dfe.md 章节 4 待补充 | 2026-08-31 |
| 0.9 | rx_init_done 拉高前的流程包含哪些内容？（rx_init_done 后认为系统正常；**与 `PHY_CAL` 无强关联**，2026-09-17 用户更正，原“与 calibration 有什么联系”已删） | 梳理中（上电入口 + PLL_READY 条件已记；RX_INIT 内部流程**已有第一版口述**，待细化顺序与判据） | 已记录硬/软复位、可选 PU（`PIN_PU`=`power_up`，input pin）、PLL_READY 前置条件（系统时钟 ready / `PHY_CAL` 结束 / `reg_cnt_pll_ready` 配置值 / ANALOG `PLL_LOCK`）、对测环境对端 ready、有效 RX 数据及 RX_INIT 握手。**2026-09-17 明确：`RX_INIT` 与 `TRX_TRAIN` 没有任何关系**（`TRX_TRAIN_INIT` 只是 train 准备：taps 初始化、opt 初始化），`RX_INIT` = 上电后让 SERDES 稳定工作的流程；`PHY_CAL` 另立 0.17（**0.9 与 `PHY_CAL` 无强关联**，2026-09-17 用户更正）。**内容基线（2026-09-17 用户强调）：以上流程整理自参考项目 RTL 代码架构，是参考项目的实现事实，不是“无 RTL 依据的口述”；本项目（自己的 RTL）是否/如何实现待另行核对。**2026-09-17 该主题已从 `questions_dfe.md` 章节 7 迁出，独立成文 → 详见 **`questions_rx_init.md`**；同日用户口述内部流程第一版（两个拉起来源 `pll_ready` 自动 / `PIN_RX_INIT_EN`；`rx_init_en` 先拉低 `rx_init_done`、DFE 完成后拉高 `RX_INIT_DONE`；`rx_init_en`→`dtl_train`→拉起一次 `cds` 完成 `dfe_train`、靠默认 FFE 值完成 FFE train；`rx_init` 期间仍需发 `txp`/`txn`；默认 FFE 值 = **寄存器初值**）。另有 `pll_ready` 的“超时即使未 lock 也拉高”= 老化保护机制。**2026-09-17 用户裁决两点**：① “taps 每次都像从 0 开始”的成因**已定案 = `cds` 中的 `reset_st` 把 taps 复位到 0**（另含 `reset dtl` 环节，属 `cds` 内的一环；不是 `cal` 被跳过、也不是加速手段）；② 需区分两个阶段——`rx_init` 完成后**产生一组 taps**，真正的 `trx_train` 开始时**复位并重新 train**（据此与 0.3 / f0_init_verification.md 的“初值 = 0”观察不冲突） | 2026-08-31；更新 2026-09-17 |
| 0.17 | `PHY_CAL` 的代码/架构整理（用户 2026-09-17：“这部分的代码还需要进一步的整理，可以留一个open”） | 待整理 | 定位：`PHY_CAL` 是**参考项目 RTL** 架构中的重要部分，用于上电后调整参数、让 PHY 能够正常工作；同时是 `PLL_READY` 形成条件之一（“`PHY_CAL` 已结束”），相关流程见 **`questions_rx_init.md`** | 2026-09-17 |
| 0.19 | 速率切换（rate / speed 切换）：在当前代码架构中的位置与内容 | 待整理 | 用户 2026-09-17：“当前代码架构中，还有个内容是速率切换，这个内容此前并没有被提到过” → 立为 open；基线 = 参考项目 RTL。**本项只登记在 `open_item.md`**（用户 2026-09-17 指定：不写入 `questions_rx_init.md`） | 2026-09-17 |
| 0.20 | CDS 六阶段的 load/save/skip 策略 | 待结合参考 RTL 与波形冻结 | 已明确 CDROPT 只恢复 phase、不直接 load taps；待逐项核对 reset/PM/EEOS/DFE/measure 的保存对象、valid 生命周期、同候选多轮测量跳过策略及 EEOS复用条件。详见 `questions_trx_train_taps.md`“CDS 六阶段 load/save/skip 新问题与建议” | 2026-09-19 |
| 0.21 | 表 A.54 “PLDB大小 3840/730 bit” 的口径解释 | 待用户确认 | 助手推算：表 A.54 按 **9B/10B（反向 8B/10B）编码后线速比特**计（384×10=3840 / 73×10=730），与 A.2 的 PLDB 3186/552 bit 是不同口径、不是数值矛盾；算式校验：3840÷各挡位速率 = 1920/1200/960/600/480/300 ns、730÷100 Mb/s = 7300 ns，与表内 t₂ 逐个吻合。**影响**：GPIO 固定时延 t₃ = T − t₁ − t₂ 的 t₂ 直接用表内 ns 值。详见 `questions_pcs.md` §3 | 2026-09-21 |
| 0.22 | 图 A.13 输出码元序（校验在前 vs 注“D0~P29”）待对原图收盘 | 待核原图 | 三处冲突：A.2.2.3“P0 为最先输出的 RS 纠错码元”、A.2.2.4 注“发送顺序从 D0~P29”、位域识别出的图 A.13 输出序列 `P0…P29、D353…D0`。**交织器/解交织器线序的硬前置条件**（原图 PDF p26 / 印刷 18）。详见 `questions_pcs.md` §2 ⚠待核 | 2026-09-21 |
| 0.23 | 图 A.10 66B 码块格式的位序与指示位位置待对原图确认 | 待核原图 | 正文只给“低 2 位为码块指示位、负荷低 4 位为子指示位”，块内位序与传输顺序需对图（原图 PDF p24 / 印刷 16）。详见 `questions_pcs.md` §5 Part 2 | 2026-09-21 |
| 0.24 | 图 A.22 优先级传输示例中 `M`、`0/1` 标号含义 | 待核原图 | 正文未文字化说明；A.2.4 只规定“截断低优先级媒体封装包、粒度=66B 码块”（原图 PDF p31 / 印刷 23）。详见 `questions_pcs.md` §5 Part 2 | 2026-09-21 |
| 0.25 | 训练期正向实际交织深度：训练期 L=1、数据传输期按反向节点配置切换？（表 A.17 正向训练帧 L 字段固定 `01` 的两种读法） | 待用户确认（需对账基线 RTL） | 读法 (a)：训练期确实以 L=1 发送，进数据传输后切到反向节点在反向训练帧里配的 L → **解交织器须支持运行中切档**；读法 (b)：该字段在正向帧中本就无语义，固定值只为确定性，实际一直按配置 L 工作。决定交织/解交织器是否需要动态切换通路。详见 `questions_pcs.md` §2、§4 | 2026-09-21 |
| 0.26 | 图 A.3 正向静默与反向静默的时序关系（是否重叠、箭头先后） | 待核原图 | 文本层无内容（原图 PDF p20 / 印刷 12）；关系到训练态"轮流静默防两方向同时开车互扰"的实现与填充 PLDB 的触发时刻。详见 `questions_pcs.md` §4 | 2026-09-21 |
| 0.27 | 训练失败后的退避路径标准未定义 | 待用户确认（标准空白） | 表 A.17 只给失败原因编码（`0`=K 码或扰码无法同步、`1`=收端权值无法收敛），未写失败后如何回退（回链路协商 / 重训 / 直接上报）；A.1.5 只规定"训练成功后进数据传输"。影响训练态状态机的失败出口设计（PDF p31 / 印刷 31）。详见 `questions_pcs.md` §4、§5 Part 2 #7 | 2026-09-21 |
| 0.28 | FCR（根的起始指数）与符号位序**标准未规定** | 待与对端/内部实现确认（标准空白） | 标准只给本原多项式（正向 x⁹+x⁴+1、反向 x⁸+x⁴+x³+x²+1），**没给 FCR、没给 g(x) 系数表、没给符号位序**（对比 802.3 Cl 91/119 连 g(x) 系数表都明文给出）。FCR=1（根 α¹…α^2t）与 FCR=0（α⁰…α^{2t−1}）是**距离相同、但 g(x) 全部系数与校验符号完全不同**的等价码：正向常数项 g₀ 由 α^465 变 α^435、反向由 α^10 变 α^6。影响：互通（两端 g(x) 不一致则纠不了错）。详见 `reference_pcs.md` §2.5、§3 | 2026-09-22 |
| 0.29 | 本项目 FEC 编解码器的实现参数待与 RTL 对账 | 待用户确认（需对账基线 RTL） | 助手估算（⚠ 需综合/面积实测核对）：正向 1.28 G 符号/s、码字 300 ns、400 MHz 下 P=3 符号/拍、编码器 ≈990 常量乘（约 3.1 万 XOR2 门）、解码器 Chien 需并行 3 路（48 常量乘）、t=15 解码器 ~5~15 万门量级。**待确认**：实际并行度 P、Chien 并行路数、是否有交织/解交织器（与 0.25 相关）、FEC 延迟是否已计入 GPIO 固定时延预算。详见 `reference_pcs.md` §2.4 | 2026-09-22 |

## 已完成（归档）

| # | 事项 | 结论 | 完成 |
|---|------|------|------|
| 0.14 | 核实 SAS SPL 原文三点：BALANCE、ERROR CODE、coefficient request 编码 | **三点均已收口**：① BALANCE 层次此前已完成；② 已从 SPL-4 r04 §5.10.3/Table 78 补齐 ERROR CODE 8bit 码表及多错误优先级，并明确 r04 未列出的空洞值 `12h/14h/16h–19h`；③ SPL-4 Table 74、COMPHY Table 8、IEEE 802.3 Table 72-4、AMD PG165 四者一致：`01=Increment`、`10=Decrement`。双方均高位先发，故并非协议字节序差异；若接口读值相反，应排查 arrival-order 与向量 bit 编号映射。详见 questions_tx_train.md §2、§9。 | 2026-09-13 |
| 0.16 | ETH RTL 增强：接收字段两帧确认、Slave 容错与位序互通验证 | **已实现并验证**：Control事务键`[13:12]+[5:0]`连续2帧相同后只提交一次；Coefficient Status`[5:0]`独立连续2帧确认；通用`remote_rx_train_complete`逐合法Status帧送入ETH三帧确认。坏帧清候选但保留上次确认值；Slave忽略相同请求并接受经确认的无Hold反向请求；Master保持请求并严格经过Hold。`rxdata_train_frame`、`tx_train_slave`、`tx_train_master`、`tx_train_link_ready`及顶层`tx_train_slave` case均PASS；帧用例确认bit15先发且`tx_data[39]`为并行字首发。外部PHY lane/byte重排仍属于具体对接工程，不在当前数字RTL内部定义。 | 2026-09-13 |
| 0.7 | tx_train：TX taps 控制/监控、帧结构、参数产生与保存 | **知识链已闭环**：Control/Status 双向归属、Master 本地 gx 步数账本、远端真实 taps 不可知、Slave 执行与状态返回、try-test-compare/opt 恢复、ETH/SAS 模式字段边界、接收过滤、Hold 重置及逻辑字段 bit15 先发均已归纳。参考项目覆盖 ETH+SAS；当前项目 RTL 只实现 ETH，SAS 的 TX_INIT/TRAIN_COMP/BALANCE 不列为当前 RTL 缺失。后续代码增强与互通验证独立转 0.16。详见 questions_dfe.md 章节 6、questions_tx_train.md §11 | 2026-09-13 |
| 0.15 | tx_frame 组帧与 Master Control 保持 | **已定稿**：组帧无状态机、固定拍数、DME 后替换、异步收发和 status 快照机制均确认。Master 不统计已发送帧数；它保持当前 Control，直到接收端交付已确认的 Status，再切 Hold 并等待 Ready。CDC 只传字段变化，TX 域锁存值在线路上连续重复。BALANCE 是 SAS 参考路径的最终字段修正，不属于当前 ETH-only RTL。详见 questions_tx_train.md §1.3-1.5、§7 | 2026-09-12/13 |
| 0.3 | f0（主抽头）冷启动初值 | P1-P5 全部确认：f0 冷启动初值 = 0（上电复位 opt/train 全 0）；正常流程 trx_train 从 0 训、本项跳过时 normal_train 从 0 起训并持续调整防掉链（RTL：09-01 taps=0 坏态两轮收敛；09-03 prbs fail→调 taps→lock）；trx_train 与 normal_train 差在是否做 rx_ffe。详见 f0_init_verification.md 结论记录 | 2026-09-03 |
| 0.11 | 初始化流程中的 dtl_train（normal_train 之前）结束时 taps 仍全为 0，原因待查 | dtl_train 是初始化流程的特殊状态；当前代码用配置 freeze taps → init 后仍全 0；freeze 意图 = 加速 init，train 留到 normal_train（寄存器默认 freeze）；去掉 freeze 则 rx_init 完成时应有粗调 taps。已记 f0_init_verification.md（用户查代码确认） | 2026-09-01 |
| 0.12 | normal_train 时 taps 怎么变化？为什么逐步调整 vs trx_train 一次性完成 | normal_train 不清空 taps、每轮在基础上累积调整（波形确认）；trx_train reset 清空重训（用户确认）。底层机制（助手推断，待后续讨论）：reset 装载源差异——dig/ana_load_ext 选 ext/reg vs saved（CDR_DFE_State.md L27-32） | 2026-09-01 |
| 0.5 | 模型调整后复测：e_dpher 去 ph_os，c_dpher 加 ph_os（默认 32 码） | **复测通过（2026-09-07 用户自测）**；吸收现象确认为模型错误（ph_os+90° 被错放进 edge 路径），真实代码 ph_os 只在 data 路径、不被 DTL 吸收直接平移采样点；结论见 questions_dfe.md 章节 2（结论区 bullet + 依据 3） | 2026-09-07 |
| 0.13 | mem/saved 能否合并 | **不能合并（2026-09-07 用户梳理确认）**：save = **本轮**测试结果（轮内局部、只被 load 状态装载）；mem = **全局**测试结果（pass 时 mem<=save 提升为全局存档，供 reset_st(dtl)/结束 ff 装载）；两者语义不同、不可相互替代，合并建议撤销。详见 questions_trx_train_taps.md mem.* 节（save vs mem 语义定稿） | 2026-09-07 |
| 0.10 | 正常 trx_train 流程中的 taps 变化梳理（train_taps↔opt_taps 更新/回灌全链路） | 全流程定稿（2026-09-07；底稿 `questions_trx_train_taps.md`）：待排查 T1-T8 全归档（f1_dfe 经同事确认 = 历史命名遗留、功能废弃；T6 入口装载、T4 reset/load 装载源、T5/T8 avg 与 dfe_cal 10 态）；主干 A-F 全定稿——A 入口：trx_train_start_st 复位 train/opt、ff 装寄存器数据（reg_dfe_fx_ext）；B 轮内：saved 仅 load 态装载、reset_st 两源 mem(dtl)/reg 无 saved；C 归档：dfe_cal 10 态、process 装载 avg→train、level 三态分工；D opt 更新 4 状态点（trx_init 重置 / tx_train 开始重置 / gain_train 直接更新 / ffe 比较更新；des=LSB 刻度）；E 回灌：load_opt_*_st 阶段性恢复；F 出口：train_taps 末次修改 = rx cdropt 后对比存 opt、normal 用 save_taps 不用 train_taps、冻结在 cds = ff 层、DTL 从 reset_st 起；mem/save 语义（save 本轮 / mem 全局）见 0.13。残余小点（sum_loop 轮数、dfe_start/dfe 语义、gx_taps 等）已标需时查 | 2026-09-07 |

## 已落盘记录索引（2026-08-31）

| 事项 | 落盘位置 |
|------|----------|
| skip_cdr 意义 = 跳过 reset 及恢复的重新训练 | questions_dfe.md 章节 2 结论区 |
| f0p 两种配置 / fn1=f0B−f0A / level 0-5 / 饱和判定 / 旁路回退判据 | questions_dfe.md 章节 4 |
| Maxf0p Update 补 `!cdr_become_worse` 前提 | Maxf0p_State.md + questions_dfe.md 章节 4 |
| Midpoint/Maxf0p Inc_index 符号与 Midpoint 跳转目标修正 | Midpoint_State.md + Maxf0p_State.md |
| 三控制器（fn1/freeze/full_sweep）与两模式关系、串联顺序、skip_cdr 状态清单 | questions_dfe.md 章节 4 结论 + 章节 2 依据 4 |
| Midpoint 阈值初值机制 / 左右阈值不对称 / k 范围约束 / 判据风格 | questions_dfe.md 章节 4 |
| taps 存储架构（opt/train/avg/saved/ext 层级与流动）+ P1 上电复位全 0 | f0_init_verification.md（taps 存储架构节 + 结论表 P1） |
| RX_INIT 上电入口、PLL_READY 前置条件、对测约束和接口握手 | **questions_rx_init.md**（2026-09-16 记录；2026-09-17 由 questions_dfe.md 章节 7 迁出；内部状态流程第一版已记录于章节 2；taps 两阶段已裁决） |
