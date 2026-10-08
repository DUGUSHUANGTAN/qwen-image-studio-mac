# 画质排查记录

这份文档记录本发行版几个默认值的来由，以及它们背后的实测数据。改参数前请先读一遍。

## 1. MPS 上编辑必须 CPU VAE

**现象。** 在 Apple Silicon 上做多图编辑，成片不是「模糊」，而是整张画布变成参考图的「浮雕 + 均匀噪点」。编辑语义部分成立，但纹理全毁。单参考图完全正常。

**定位。** 用不经过扩散模型的纯 VAE 编解码往返测试复现（encode → decode，不采样）：

| 配置 | 尺寸 | PSNR |
|---|---|---|
| MPS VAE | 1376×768 | **9.23 dB** |
| CPU VAE | 1376×768 | **43.96 dB** |

问题出在 VAE 编解码环节，与提示词语言、步数、画布来源、注意力后端均无关。切换 PyTorch attention 实现为完整双图/40 步对照仍然坏，已撤回该实现。

**修复。**

- Mac 自动启动 ComfyUI 时追加 `--cpu-vae`，只有 VAE 跑 CPU，扩散模型仍用 GPU（`server.py` 的 `ComfyBackend.resolve`）。
- 复用已有服务时通过 `/system_stats` 检查真实设备类型和启动参数（`ComfyBackend._safe_for_edit`）。显式 URL 配置若不满足条件则**拒绝**并提示如何修正；本地文件夹配置会自动另启一个安全服务。

**为什么必须这么较真。** ComfyUI 在 MPS 上跑坏 VAE 时**不报错**，只是静默产出损坏数据。少了这层检查，用户会以为是自己提示词写���了。

## 2. 默认 40 步

官方 Qwen-Image-2.1 模型卡的 `num_inference_steps=40`；ComfyUI 内置模板用 25 步。25 步读作模糊，实际���是预览档。

`clean_settings()` 的默认值同步为 40，`validate_edit_settings()` 阻止低于 25 步的编辑——目的是防止用户误套其他蒸馏模型的少步配方。

## 3. 编辑画布约 1 MP

官方编辑配方把参考图缩放到约 1 MP（`TextEncodeQwenImage21` 的 `resolution=1024`）。画布远大于参考图的条件分辨率，会让编辑区域清晰而周边发软。

原先编辑模式选比例时套用文生图的 4 MP `RATIO_SIZES`，是「中间清晰四周发糊」的根因。现改为按 `EDIT_PIXEL_BUDGET`（约 1 MP）换算，并同步前端的 `plannedSize` 与 `recommendedEditSize`。

`validate_edit_settings()` 阻止超过 1.5 MP 的自定义编辑画布。**这是本软件的质量保护策略，不是 Qwen 模型的能力上限**——建议先在 1 MP 完成编辑再放大。

## 4. 官方参数 vs 软件策略

区分清楚很重要：

- **官方参数**：40 步、CFG 1、Euler/simple、denoise 1、`resolution=1024`。
- **软件策略**：25 步下限、1.5 MP 画布上限、必填宽高成对校验、CPU VAE 强制。

两者都在 UI 文档和 README 里分别标注。改动任一阈值前，确认它属于哪一类。

## 已排除的假设

记录下来避免重复排查：

- **KV cache**：关闭后同样坏图。
- **ComfyUI 版本**：升级到 v0.38.1（含 Qwen KV cache、per-block attention 修复）后复测仍坏，已回退 v0.37.4。
- **布尔遮罩语义差异**：单独切换该实现仍坏，不是画质根因。
- **int8_convrot 混合精度**：未验证，仍是理论上的可能原因。

真实双图换人任务的验收一度未通过——语义成立但纹理损坏，在第 1 项修复后已恢复正常。

## 验证方式

```bash
app/.venv/bin/python app/verify_params.py          # 参数确实落进节点图
app/.venv/bin/python -m unittest discover -s tests # 回归测试
```

两者都不需要 GPU 和运行中的 ComfyUI。改了 `build_comfy_graph` 或 `clean_settings` 之后务必都跑一遍。