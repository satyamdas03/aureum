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
    <div className="h-full min-h-[400px] rounded-lg overflow-hidden border border-aureum-panel">
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
        }}
        onChange={(v) => onChange(v || "")}
      />
    </div>
  );
}
