import reflex as rx

config = rx.Config(
    app_name="safari",
    show_built_with_reflex=False,
    # WebSocket keep-alive settings to prevent silent disconnects
    websocket_ping_interval=30,   # Send ping every 30 seconds
    websocket_pong_timeout=60,    # Connection dead if no pong within 60 seconds
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
    ]
)