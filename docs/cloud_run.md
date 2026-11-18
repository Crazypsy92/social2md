# Social2MD 云端运行指南（当前 Douyin 适配器）

## 运行范围

当前云端入口 cloud_runner.py 仅连接 Douyin/F2 下载接口。Social2MD 的项目定位是多平台归档，但 Bilibili 和小红书尚未接入这个运行器；不要将它当作通用 URL 下载器。

## 运行方式

云端入口为 cloud_runner.py，与当前抖音脚本 douyin2txt.py 共用转录和 Markdown 处理能力。

在 Codex Cloud 的安全环境变量中配置 DOUYIN_COOKIE。不要把 Cookie 写进任务提示词、命令参数、日志或 GitHub。也可以使用被 .gitignore 忽略的 douyin_cookie.yaml，但云端优先推荐 Secret 环境变量。

先执行 python cloud_runner.py --help 查看参数。真实下载前，先使用小规模验证，例如设置 --batch-size 30 --max-items 30。主页链接通过 -u 传入，博主目录名通过 -b 传入。

## 默认处理策略

- 每批最多获取 30 个作品元数据，不会一次下载 30 个视频；逐个下载、转录和校验。
- 每个作品单独下载、校验、转录和写入 Markdown。
- 同一时刻只执行一个视频转录任务。
- 只有 Markdown 通过内容校验且质量指标未触发复核阈值，才删除视频。
- 转录为空、转录异常、文件校验失败或低置信度时保留视频。
- 成功作品以作品 ID 记录，避免重复下载和重复转录。
- 分页游标和作品状态写入 state/，异常退出后可恢复。
- 已完成扫描后再次运行会提示完成；使用 --refresh 从最新作品重新扫描，已完成作品仍按 ID 去重。

## 磁盘保护

默认磁盘使用率达到 95% 暂停，恢复阈值为 90%，并至少保留 1 GiB 可用空间。项目目录、下载目录、输出目录、状态目录、临时目录和模型缓存所在文件系统都会被检查；相同文件系统只统计一次。

暂停时不会无限等待，也不会删除已完成 Markdown。空间恢复后重新启动相同命令即可继续。

## 输出

- 视频缓存：videos/
- Markdown：output/
- 断点状态：state/
- Markdown 检查点 ZIP：exports/

ZIP 只包含 Markdown，不包含视频、Cookie、模型和运行数据库。云端工作目录可能是临时环境，重要 ZIP 应在任务结束前导出到用户可持久保存的位置。
