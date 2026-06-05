from backend.main import create_app


app = create_app(prepare=True, plugin_runtime=True)
