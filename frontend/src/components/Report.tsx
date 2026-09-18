import { IconDoc } from "./icons";

interface ReportProps {
  answer: string;
  error: string | null;
}

/** 最终回答展示。 */
export function Report({ answer, error }: ReportProps) {
  return (
    <section className="report-block">
      <div className="section-head">
        <span className="section-head-icon tone-teal" aria-hidden="true">
          <IconDoc size={17} />
        </span>
        <h2 className="section-title">最终回答</h2>
      </div>
      <div className={`report${error ? " has-error" : ""}`}>
        {answer || (error ? `运行失败：${error}` : "（报告生成后将在此展示）")}
      </div>
    </section>
  );
}
