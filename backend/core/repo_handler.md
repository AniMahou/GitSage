┌─────────────────────────────────────────────────────────────────┐
│                     REPO HANDLER — Full Flow                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  User provides: "https://github.com/psf/requests"               │
│       │                                                          │
│       ▼                                                          │
│  ┌─────────────────┐                                             │
│  │  validate_url() │  Is it a real URL? Is the host valid?      │
│  └────────┬────────┘                                             │
│           │ ✅ Valid                                              │
│           ▼                                                      │
│  ┌─────────────────┐                                             │
│  │ check_repo_     │  Does the repo exist? Is it public?        │
│  │ accessible()    │  Uses: git ls-remote (lightweight)         │
│  └────────┬────────┘                                             │
│           │ ✅ Accessible                                         │
│           ▼                                                      │
│  ┌─────────────────┐                                             │
│  │    clone()      │  Downloads repo to:                         │
│  │                 │  data/repos/{session_id}/                   │
│  │                 │  depth=1 (latest only, fast)               │
│  │                 │  single_branch=True (less data)            │
│  └────────┬────────┘                                             │
│           │ ✅ Cloned                                             │
│           ▼                                                      │
│  ┌─────────────────┐                                             │
│  │ get_source_     │  Walks the file tree                        │
│  │ files()         │  Filters: supported extensions              │
│  │                 │  Skips: .git, node_modules, __pycache__    │
│  └────────┬────────┘                                             │
│           │ ✅ Found 127 .py files                                │
│           ▼                                                      │
│  ┌─────────────────┐                                             │
│  │ get_file_stats()│  Counts files, lines, chars                │
│  └─────────────────┘                                             │
│                                                                  │
│  Returns: repo_path, list of 127 file paths, stats dict          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘