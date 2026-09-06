"""One source for actual worker flags and the model-free sandbox preflight."""


def permission_args(policy):
    if policy == "readonly-network":
        # Legacy --sandbox/sandbox_mode takes precedence over named permissions.
        return [
            "-c",
            'default_permissions="pocket-readonly"',
            "-c",
            'permissions.pocket-readonly.extends=":read-only"',
            "-c",
            "permissions.pocket-readonly.network.enabled=true",
        ]
    if policy not in ("read-only", "workspace-write"):
        raise ValueError(f"Unknown command policy: {policy}")
    return ["-c", f'sandbox_mode="{policy}"'] + (
        ["-c", "sandbox_workspace_write.network_access=true"] if policy == "workspace-write" else []
    )


def fleet_exec_args(args, final):
    """Replace only Fleet's known legacy read-only flag; reject policy drift."""
    args = list(args)
    if "exec" not in args:
        return args
    separator = args.index("--") if "--" in args else len(args)
    options = args[:separator]
    positions = [i for i, arg in enumerate(options) if arg in ("--sandbox", "-s")]
    if len(positions) != 1 or options[positions[0] + 1] != "read-only":
        raise ValueError("Unexpected Fleet sandbox: expected one explicit read-only flag")
    if any("sandbox_mode=" in arg or "default_permissions=" in arg for arg in options):
        raise ValueError("Unexpected Fleet permission override")
    del args[positions[0] : positions[0] + 2]
    i = args.index("exec") + 1
    args[i:i] = [
        "--json",
        "--output-last-message",
        str(final),
        "-c",
        "features.multi_agent=false",
        "-c",
        'web_search="disabled"',
        *permission_args("readonly-network"),
    ]
    return args
