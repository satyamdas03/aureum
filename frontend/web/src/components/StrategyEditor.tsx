import Editor from "@monaco-editor/react";

interface StrategyEditorProps {
  value: string;
  onChange: (value: string) => void;
  readOnly?: boolean;
}

export default function StrategyEditor({
  value,
  onChange,
  readOnly = false,
}: StrategyEditorProps) {
  return (
    <div className="h-full w-full overflow-hidden bg-ink">
      <Editor
        value={value}
        language="yaml"
        theme="vs-dark"
        options={{
          minimap: { enabled: false },
          readOnly,
          fontSize: 13,
          fontFamily: "JetBrains Mono, monospace",
          lineNumbers: "on",
          roundedSelection: false,
          scrollBeyondLastLine: false,
          automaticLayout: true,
          padding: { top: 16 },
          renderLineHighlight: "line",
          matchBrackets: "always",
        }}
        onChange={(v) => onChange(v || "")}
        loading={
          <div className="h-full flex items-center justify-center text-slate font-mono-data text-mono-data">
            Loading editor…
          </div>
        }
      />
    </div>
  );
}
