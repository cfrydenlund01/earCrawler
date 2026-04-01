# VS Code Tunnels Setup

This guide sets up `VS Code Tunnels` so you can open this machine's real filesystem from another Windows computer in VS Code without exposing SSH or RDP.

Host details this guide is based on:

- OS: `Windows 11 Home`
- VS Code CLI: `D:\VSCode\bin\code.cmd`
- Current tunnel status: not running
- Current tunnel service status: not installed

## What You Get

From the other Windows computer, you will open a normal local VS Code window that is attached to this machine.

- Files are opened from this machine's actual disks, for example `D:\AI\rComp`
- Terminals, tasks, git, debuggers, and workspace extensions run on this machine
- No inbound port forwarding is normally required

This is not a full remote desktop. It is remote development against the host filesystem.

## Prerequisites

You need the same Microsoft account or GitHub account available on both machines.

On this machine:

- VS Code installed
- Internet access
- Keep the machine powered on

On the client Windows computer:

- VS Code installed
- Sign in to the same account in VS Code
- Install the `Remote - Tunnels` extension if VS Code does not prompt automatically

## One-Time Setup On This Machine

Open `PowerShell` on this machine and run:

```powershell
& 'D:\VSCode\bin\code.cmd' tunnel user login --provider microsoft
```

If you prefer GitHub auth instead:

```powershell
& 'D:\VSCode\bin\code.cmd' tunnel user login --provider github
```

That command will prompt you to authenticate in the browser.

Confirm the signed-in account if you want to verify it:

```powershell
& 'D:\VSCode\bin\code.cmd' tunnel user show
```

## Start A Tunnel Manually

Run this on the host machine:

```powershell
& 'D:\VSCode\bin\code.cmd' tunnel --name rcomp-host --accept-server-license-terms
```

Notes:

- Replace `rcomp-host` with any host name you want
- Leave that PowerShell window open while the tunnel is running
- Add `--no-sleep` if you want VS Code to try to prevent sleep while that process is active

Example:

```powershell
& 'D:\VSCode\bin\code.cmd' tunnel --name rcomp-host --accept-server-license-terms --no-sleep
```

## Keep The Tunnel Running After Logoff Or Reboot

If you want the tunnel to survive logoff and start automatically, install the tunnel service on this machine:

```powershell
& 'D:\VSCode\bin\code.cmd' tunnel service install --name rcomp-host --accept-server-license-terms
```

Check status:

```powershell
& 'D:\VSCode\bin\code.cmd' tunnel status
```

View service logs:

```powershell
& 'D:\VSCode\bin\code.cmd' tunnel service log
```

## Connect From The Other Windows Computer

1. Open VS Code on the other computer.
2. Sign in with the same Microsoft or GitHub account used on the host.
3. Install or enable the `Remote - Tunnels` extension if needed.
4. Open the Command Palette with `Ctrl+Shift+P`.
5. Run `Remote Tunnels: Connect to Tunnel...`
6. Select the machine name, for example `rcomp-host`.
7. After connection, run `File: Open Folder...`
8. Open the host folder you want, for example `D:\AI\rComp`

After that, the Explorer, integrated terminal, debugger, and workspace extensions operate on the host machine.

## Browser Option

You can also connect through the web by signing into:

- `https://vscode.dev`

Then connect to the registered tunnel from there. This is useful when you do not have desktop VS Code installed on the client, but desktop VS Code is usually the better experience on Windows.

## Useful Commands On The Host

Show tunnel status:

```powershell
& 'D:\VSCode\bin\code.cmd' tunnel status
```

Restart a running tunnel:

```powershell
& 'D:\VSCode\bin\code.cmd' tunnel restart
```

Stop a running tunnel:

```powershell
& 'D:\VSCode\bin\code.cmd' tunnel kill
```

Rename the registered machine:

```powershell
& 'D:\VSCode\bin\code.cmd' tunnel rename rcomp-host
```

Unregister this machine from the tunnel service:

```powershell
& 'D:\VSCode\bin\code.cmd' tunnel unregister
```

Remove the installed service:

```powershell
& 'D:\VSCode\bin\code.cmd' tunnel service uninstall
```

## Reboot And Recovery

If you install the tunnel as a service, you can reboot this machine remotely from the VS Code tunnel session and reconnect after Windows comes back up.

This is the recommended pattern:

- Do not depend on the host VS Code desktop window staying open
- Run the tunnel as a service
- Use the remote integrated terminal to restart the host when needed

Install the tunnel as a service on the host:

```powershell
& 'D:\VSCode\bin\code.cmd' tunnel user login --provider microsoft
& 'D:\VSCode\bin\code.cmd' tunnel service install --name rcomp-host --accept-server-license-terms
```

Then, from the remote VS Code session connected through the tunnel, restart the host with either:

```powershell
shutdown /r /t 0 /f
```

or:

```powershell
Restart-Computer -Force
```

Expected behavior:

- Your tunnel session disconnects during shutdown
- Windows restarts
- The tunnel service starts automatically after boot
- You reconnect from the remote computer using `Remote Tunnels: Connect to Tunnel...`

Important limits:

- If the host is frozen hard enough that the tunnel is already down, you cannot use VS Code Tunnels alone to recover it
- VS Code Tunnels is not an out-of-band management tool like IPMI, iDRAC, or a KVM
- If Windows boots but networking fails, the tunnel will not come back until network access returns

Recommended recovery path:

- Primary workflow: `VS Code Tunnels`
- Backup control path: `RustDesk`, `AnyDesk`, `Chrome Remote Desktop`, or another remote-control tool
- Last-resort power recovery: BIOS option such as `Restore on AC Power Loss` plus a smart plug, if the hardware supports it

The main operational benefit here is that the host's VS Code desktop app does not need to be running. The tunnel service is separate from the local GUI, so a host-side VS Code window crash does not by itself take down your remote development path.

## What To Expect

- This does not give you the full Windows desktop of the host
- GUI apps do not become remotely interactive the way they would over RDP
- VS Code itself is local on the client, but it is attached to the files and runtime on the host
- Only one user or client should treat the tunnel as active at a time

## Recommended Setup For This Machine

Use the service install option so the tunnel is available even after reboot:

```powershell
& 'D:\VSCode\bin\code.cmd' tunnel user login --provider microsoft
& 'D:\VSCode\bin\code.cmd' tunnel service install --name rcomp-host --accept-server-license-terms
& 'D:\VSCode\bin\code.cmd' tunnel status
```

Then connect from the other Windows computer through VS Code and open `D:\AI\rComp`.

## References

- https://code.visualstudio.com/docs/remote/tunnels
- https://code.visualstudio.com/docs/remote/vscode-server
