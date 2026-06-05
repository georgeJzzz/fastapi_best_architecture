from fastapi import FastAPI

from backend.core.registrar import register_app
from backend.plugin import plugin_lifecycle
from backend.utils.console import console
from backend.utils.timezone import timezone


def _get_log_prefix() -> str:
    """获取启动日志前缀"""
    return f'{timezone.to_str(timezone.now(), "%Y-%m-%d %H:%M:%S.%M0")} | {"INFO": <8} | - | '


def prepare_plugins() -> None:
    """检查必需插件并安装缺失依赖"""
    from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
    from rich.text import Text

    log_prefix = _get_log_prefix()

    console.print(Text(f'{log_prefix}检查必需插件...', style='bold cyan'))

    plugin_lifecycle.check_required()

    console.print(Text(f'{log_prefix}检测插件依赖...', style='bold cyan'))

    plugins = plugin_lifecycle.discover()

    with Progress(
        SpinnerColumn(finished_text=f'[bold green]{log_prefix}插件准备就绪[/]'),
        TextColumn('{task.description}'),
        TextColumn('{task.completed}/{task.total}', style='bold green'),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task('安装插件依赖...', total=len(plugins))
        for plugin in plugins:
            progress.update(task, description=f'[bold magenta]安装插件 {plugin} 依赖...[/]')
            plugin_lifecycle.install_requirements(plugin)
            progress.advance(task)
        progress.update(task, description='[bold green]-[/]')

    console.print(Text(f'{log_prefix}启动服务...', style='bold magenta'))


def create_app(*, prepare: bool = False, plugin_runtime: bool = False) -> FastAPI:
    """创建 FastAPI 应用，按需执行运行时插件准备。"""
    if prepare:
        prepare_plugins()
    return register_app(plugin_runtime=plugin_runtime)


app = create_app()
