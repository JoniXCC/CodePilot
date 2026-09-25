export function TestResults({ command, passed, output }: { command: string | null; passed: boolean | null; output: string | null }) {
  if (!command) return <p className="muted">No test command was detected for this project, so tests were not run.</p>;
  return (
    <div>
      <p className={passed ? "test-pass" : "test-fail"}>
        {passed ? "✓ Tests passed" : "✗ Tests failed"} <code>{command}</code>
      </p>
      {output && (
        <details>
          <summary>Test output</summary>
          <pre className="output">{output}</pre>
        </details>
      )}
    </div>
  );
}
