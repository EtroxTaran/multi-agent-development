/**
 * Settings page
 */

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Separator,
} from "@/components/ui";

export function SettingsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Settings</h1>
        <p className="text-muted-foreground">
          Configure your Conductor dashboard
        </p>
      </div>

      <Separator />

      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>API Connection</CardTitle>
            <CardDescription>Backend API configuration</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div className="flex justify-between">
                <span className="text-muted-foreground">API URL</span>
                <span className="font-mono text-sm">/api</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">WebSocket</span>
                <span className="font-mono text-sm">
                  /api/projects/:name/events
                </span>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Database</CardTitle>
            <CardDescription>SurrealDB configuration</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Status</span>
                <span className="text-green-600">Connected</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">URL</span>
                <span className="font-mono text-sm">
                  ws://localhost:8000/rpc
                </span>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Agent CLIs</CardTitle>
            <CardDescription>Agent command-line tools</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Claude</span>
                <span className="font-mono text-sm">claude</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Cursor</span>
                <span className="font-mono text-sm">cursor-agent</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Gemini</span>
                <span className="font-mono text-sm">gemini</span>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>About</CardTitle>
            <CardDescription>Dashboard information</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Version</span>
                <span>1.0.0</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Frontend</span>
                <span>React + Vite</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Backend</span>
                <span>FastAPI</span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
