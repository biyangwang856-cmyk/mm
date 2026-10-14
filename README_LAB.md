# 实验室 MicMac 航拍正射流程

完整的本次运行说明、文件作用和复现命令见 [lab_pipeline/README-mangrove077.md](lab_pipeline/README-mangrove077.md)。
本仓库保留官方 MicMac 源码与许可证、实验室运行脚本，以及已有本地 Git 检查点历史。

## 来源和范围

- 官方源码：micmacIGN/micmac，固定提交 `f8fe432101fb1852f8c4d8546504a5278f6ef57f`。
- 采用官方固定版本压缩包建立本地 Git 快照，没有导入上游全部提交历史。
- 输入实验：405 张 DJI M4E 航拍照片，全部用于定位与表面重建，160 张垂直照片用于正射颜色。
- 原始照片、导航文件、编译产物、缓存和重建结果由服务器与 D 盘备份保管，不纳入这个代码仓库。
- 3 厘米是目标输出像元采样间距，没有独立 GCP 绝对精度验收。

## 服务器目录和运行

```bash
cd /volume/wzhang/mesh-research-workspace/micmac
bash lab_pipeline/build_micmac.sh
python3 lab_pipeline/monitor.py
```

服务器已经安装运行依赖。`lab_pipeline/install_dependencies.sh` 记录初次搭建时使用的临时代理 `127.0.0.1:17995`，该代理目前已关闭；重新安装前需按网络环境修改脚本中的 `apt_options` 或恢复代理，并确认 CMake 可用。

数据准备使用 `lab_pipeline/prepare_dataset.py`；输入数据不存在时不能仅靠代码仓库完成重建。
确认没有活跃流程后，可从同一输入的已有检查点恢复：

```bash
python3 lab_pipeline/launch_job.py pipeline nice -n 10 /usr/bin/python3 -u lab_pipeline/run_all.py
```

照片或关键参数改变时使用新的运行目录，不复用旧实验的检查点。
运行流水线依次完成 GPS 提取、匹配、SfM 自标定、GPS 束调整、坐标变换、Malt 密集匹配与正射校正、Tawny 拼接、GeoTIFF 导出和结果验证。

## 回退检查点

`0c173c2` 修复了再次释放全部内参造成的畸变反演失败：保留 Tapas 已求的内参，Campari 使用 `AllFree=0`。
修复前代码标签为 `checkpoint/pre-fixed-ba-20261014`（`29c27c8`）。
完整历史保留在本仓库，使用标签即可检查旧版本。不要在活跃重建中切换其工作目录的代码。

```bash
git log --oneline
git show checkpoint/pre-fixed-ba-20261014:lab_pipeline/run_micmac.py
```

GitHub 仅用于代码和流程版本管理，实际运行状态由服务器 `lab_runs/mangrove-077-full405/status.json` 决定。
不能依据某个代码提交就判断最终正射已经生成。
