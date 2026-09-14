interface ReportProps {
  answer: string;
  error: string | null;
}

/** 最终回答展示。 */
export function Report({ answer, error }: ReportProps) {
  return (
    <section className="report-block">
      <div className="block-label">最终回答</div>
      <div className="report">
        {answer || (error ? `运行失败：${error}` : "（报告生成后将在此展示）")}
      </div>
    </section>
  );
}
