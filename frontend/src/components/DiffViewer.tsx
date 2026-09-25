/** Renders a unified diff with added/removed lines highlighted, grouped per file. */

interface FileDiff {
  path: string;
  lines: string[];
  added: number;
  removed: number;
}

const HUNK_HEADER = /^@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@/;

/**
 * Parses git-style and difflib-style unified diffs. Hunk headers say how many old/new
 * lines follow, so a removed line that happens to start with "--" is never mistaken
 * for the next file's header.
 */
export function parseDiff(diff: string): FileDiff[] {
  const files: FileDiff[] = [];
  let current: FileDiff | null = null;
  let oldLeft = 0;
  let newLeft = 0;

  for (const line of diff.split("\n")) {
    const inHunk = oldLeft > 0 || newLeft > 0;
    if (inHunk && current) {
      current.lines.push(line);
      if (line.startsWith("+")) {
        current.added++;
        newLeft--;
      } else if (line.startsWith("-")) {
        current.removed++;
        oldLeft--;
      } else if (!line.startsWith("\\")) {
        oldLeft--;
        newLeft--;
      }
      continue;
    }

    const hunk = HUNK_HEADER.exec(line);
    if (hunk && current) {
      oldLeft = hunk[1] === undefined ? 1 : Number(hunk[1]);
      newLeft = hunk[2] === undefined ? 1 : Number(hunk[2]);
      current.lines.push(line);
    } else if (line.startsWith("diff --git") || (line.startsWith("--- ") && (!current || current.lines.length > 0))) {
      current = { path: "", lines: [], added: 0, removed: 0 };
      files.push(current);
      if (line.startsWith("--- ") && line !== "--- /dev/null") current.path = line.slice(4).replace(/^a\//, "");
    } else if (line.startsWith("+++ ") && current) {
      current.path = line.slice(4).replace(/^b\//, "");
    }
  }
  return files.filter((file) => file.lines.length > 0);
}

function lineClass(line: string): string {
  if (line.startsWith("@@")) return "diff-hunk";
  if (line.startsWith("+")) return "diff-add";
  if (line.startsWith("-")) return "diff-del";
  return "diff-ctx";
}

export function DiffViewer({ diff }: { diff: string | null }) {
  const files = diff ? parseDiff(diff) : [];
  if (files.length === 0) return <p className="muted">No changes.</p>;
  return (
    <div className="diff">
      {files.map((file, index) => (
        <div className="diff-file" key={`${file.path}-${index}`}>
          <div className="diff-file-header">
            <code>{file.path || "(unknown file)"}</code>
            <span className="diff-stats">
              <span className="diff-stat-add">+{file.added}</span> <span className="diff-stat-del">−{file.removed}</span>
            </span>
          </div>
          <pre className="diff-body">
            {file.lines.map((line, i) => (
              <div key={i} className={lineClass(line)}>
                {line || " "}
              </div>
            ))}
          </pre>
        </div>
      ))}
    </div>
  );
}
