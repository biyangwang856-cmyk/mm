# 405 张红树林照片的独立 MicMac 正射流程

项目目录：`/volume/wzhang/mesh-research-workspace/micmac`。
原片来自 `../datasets/DJI_202610101454_077_1010红树林`。
这是 2026-10-10 的新场景，不是以前 353 张 FT-070 照片的结果。

## 来源与输入

官方仓库：<https://github.com/micmacIGN/micmac>。
固定源码提交：`f8fe432101fb1852f8c4d8546504a5278f6ef57f`。
`source_provenance.json` 记录官方压缩包地址、提交和压缩包 SHA256。
当前网络下采用官方固定提交的完整源码压缩包，建立本地 Git 快照；
本仓库没有导入官方全部历史。没有推送远端。

`lab_data/mangrove-077/images` 是 405 张原始照片的独立复制，
`ancillary` 保留 5 个导航文件；每个文件都与原文件校验 SHA256。
数据、编译目录和运行产物在 `.git/info/exclude` 排除，代码单独版本管理。

元数据核实：DJI M4E，5280×3956，405 张都有 GPS，
其中 160 张云台俯仰角 -90°，其他为 -60°、-45°。
全部照片用于匹配、SfM 和稠密表面；160 张垂直照片用于正射颜色。
Exif 的 35mm 等效焦距用于 MicMac 原生内参初始化，之后自标定；
DJI XMP 内参保留为参考，没有手工改写照片元数据。

## 文件和修改入口

| 文件或目录 | 作用 |
|---|---|
| `lab_pipeline/prepare_dataset.py` | 独立复制、原片 SHA256 校验、Exif/XMP 提取 |
| `lab_pipeline/build_micmac.sh` | CPU Release 编译和安装，关闭 Qt/CUDA/OpenCL |
| `lab_pipeline/run_micmac.py` | 12 阶段重建入口、参数、日志、输入签名和可恢复检查点 |
| `lab_pipeline/run_all.py` | 等待编译成功、执行重建、执行最终文件验证 |
| `lab_pipeline/launch_job.py` | 启动脱离 SSH 连接的服务器任务 |
| `lab_pipeline/monitor.py` | 读取当前阶段和日志，不修改重建数据 |
| `lab_pipeline/verify_orthophoto.py` | 验证相机数、旋转矩阵、坐标、像元间距、RGB 和完整文件 SHA256 |
| `src/uti_phgrm/` | MicMac 原生定位、密集匹配、正射等算法实现 |
| `include/XML_MicMac/` | 原生算法的参数模板 |
| `lab_runs/mangrove-077-full405/config.json` | 本次实际运行参数与来源 |
| `lab_runs/mangrove-077-full405/status.json` | 各阶段命令、耗时和完成状态 |
| `lab_runs/mangrove-077-full405/logs` | 每一步完整原生日志 |
| `lab_runs/mangrove-077-full405/Ori-*` | GPS 原始位置、SfM 和最终相机姿态 |
| `lab_runs/mangrove-077-full405/MEC-Malt` | 稠密表面、掩膜和对应的高度量纲参数 |
| `lab_runs/mangrove-077-full405/Ortho-MEC-Malt` | 单张校正影像、可见性/入射角和原生拼接影像 |
| `lab_runs/mangrove-077-full405/OUTPUT` | 最终 GeoTIFF、预览与验证报告 |

## 本次完整原生流程

1. `XifGps2Txt` 读取 GPS 到文本。
2. `XifGps2Xml` 建立局部坐标和原始相机位置。
3. `OriConvert` 按 GPS 距离 100 米产生候选匹配对。
4. `Tapioca File` 使用长边 2640 像素图像匹配，全量 405 张照片。
5. `Tapas FraserBasic` 从匹配重新估计相机，不使用 ODX 相机。
6. `CenterBascule` 用 GPS 对齐相机模型。
7. `Campari` 保留 Tapas 求得的内参，只调整相机姿态和结构，GPS 标准差权重设为 5 米。
8. `ChgSysCo` 变换到由照片中心经纬度确定的 WGS84 UTM 坐标。
9. `Malt Ortho` 稠密表面和正射校正，`ResolTerrain=0.03 EZA=1 ZoomF=2`。
10. `Tawny` 原生拼接，`RadiomEgal=0`。
11. `gdal_translate` 写带投影的分块、DEFLATE 压缩 GeoTIFF，保留原生完整范围。
12. 生成缩略预览，再运行独立验证。全分辨率文件不经过缩略图放大。

运行用 64 个任务并发，内部 OpenMP/OpenBLAS/ImageMagick 线程设为 1，
避免嵌套线程无上限扩张。任务以 nice=10 运行，SSH 断线不会中止。
MicMac 这条流程主要用 CPU，不要求 H100 提供 CUDA 计算。

## 复现和恢复

```bash
cd /volume/wzhang/mesh-research-workspace/micmac
bash lab_pipeline/build_micmac.sh
/usr/bin/python3 lab_pipeline/run_micmac.py --threads 64 --resolution 0.03
/usr/bin/python3 lab_pipeline/verify_orthophoto.py
```

查看当前状态：

```bash
/usr/bin/python3 lab_pipeline/monitor.py
```

### 2026-10-14 束调整恢复

原先第 7 步使用 `AllFree=1` 再次释放全部内参，在影像边角的畸变逆变换中
发生 NaN 和不收敛，未导出最终相机。此前第 1–6 步已完成，405 张相机都已注册。
改为 `--ba-calibration-mode fixed`（`AllFree=0`），固定第 5 步已经自标定的内参。
这不跳过 GPS 束调整，也不代表质量已经通过验收。

恢复入口 `run_all.py` 使用 `--recover-failed-ba`。检查点迁移只允许输入、尺度、GPS 权重等
其他签名完全一致、第 1–6 步完成、第 7 步失败且第 8 步之后未开始的情况。
迁移前自动复制原状态、配置和失败日志到 `recovery_history`，随后逐项验证并复用第 1–6 步。
已完成束调整的实验更换内参模式时必须另建运行目录。

修改前的 Git 标签为 `checkpoint/pre-fixed-ba-20261014`，完整运行快照保存在
`../backups/micmac-20261014`。停止本次任务后可在新工作树检查旧代码：

```bash
git worktree add ../micmac-pre-fixed-ba checkpoint/pre-fixed-ba-20261014
```

新工作树只包含受 Git 管理的代码，不包含原片或缓存；完整数据恢复应使用完整备份。
勿在重建运行中切换或回退其正在读取的工作目录。

只在已有进程结束后恢复，不要重复启动：

```bash
/usr/bin/python3 lab_pipeline/launch_job.py pipeline nice -n 10 /usr/bin/python3 -u lab_pipeline/run_all.py
```

参数或照片变化时必须新建运行目录，不能复用旧检查点：

```bash
/usr/bin/python3 lab_pipeline/run_micmac.py --run-name mangrove-077-new-experiment --threads 64 --resolution 0.03
```

每一步的准确命令以运行目录 `status.json` 为准。
Malt 完成检查验证 `MTDOrtho.xml`、DSM，以及每张 `Ort`、`PC`、`Incid` 文件；
`Param-Tawny.xml` 是软件模板，不是 Malt 必须输出的产物。

## 解释边界

3 厘米是输出采样间距，不等于 3 厘米绝对定位精度。
没有独立地面控制点的精度验收。导航/RTK 辅助文件被完整保留，
这次原生流程用照片 Exif GPS，没有额外执行 PPK 解算。
静态重建和原生拼接不保证消除移动车辆、树冠运动、遮挡或未观测区域。
完整输出指保留本次原生重建和拼接的全部范围，不裁剪缺陷，也不补造未观测结构。
应在运行成功后查看原分辨率细节，才可判断是否优于其他方法。
