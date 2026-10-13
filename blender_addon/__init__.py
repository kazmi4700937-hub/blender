bl_info = {
    "name": "Rigging Assistant Bridge",
    "author": "Antigravity Team",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > Rig Assistant",
    "description": "Bridge server for 2D-to-3D Character Rigging Assistant",
    "category": "Development",
}

import bpy
from . import server

class RigAssistantPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    host: bpy.props.StringProperty(
        name="Host",
        default="127.0.0.1",
        description="Bridge socket host"
    )
    port: bpy.props.IntProperty(
        name="Port",
        default=9876,
        min=1024,
        max=65535,
        description="Bridge socket port"
    )
    allow_exec: bpy.props.BoolProperty(
        name="Allow Python Exec (Dev Only)",
        default=False,
        description="Allow arbitrary python execution over bridge (dev only)"
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "host")
        layout.prop(self, "port")
        layout.prop(self, "allow_exec")

class WM_OT_RigAssistantStartServer(bpy.types.Operator):
    bl_idname = "wm.rig_assistant_start_server"
    bl_label = "Start Bridge Server"
    bl_description = "Starts the local TCP bridge server"

    def execute(self, context):
        prefs = context.preferences.addons[__name__].preferences
        server.start_server(host=prefs.host, port=prefs.port, allow_exec=prefs.allow_exec)
        self.report({'INFO'}, f"Bridge server running on {prefs.host}:{prefs.port}")
        return {'FINISHED'}

class WM_OT_RigAssistantStopServer(bpy.types.Operator):
    bl_idname = "wm.rig_assistant_stop_server"
    bl_label = "Stop Bridge Server"
    bl_description = "Stops the local TCP bridge server"

    def execute(self, context):
        server.stop_server()
        self.report({'INFO'}, "Bridge server stopped")
        return {'FINISHED'}

classes = (
    RigAssistantPreferences,
    WM_OT_RigAssistantStartServer,
    WM_OT_RigAssistantStopServer,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    # Auto-start server with defaults on add-on registration
    try:
        prefs = bpy.context.preferences.addons[__name__].preferences
        server.start_server(host=prefs.host, port=prefs.port, allow_exec=prefs.allow_exec)
    except Exception as e:
        server.start_server(host="127.0.0.1", port=9876, allow_exec=False)

def unregister():
    server.stop_server()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
