import { UploadZone } from "@/components/upload-zone";

export default function UploadPage() {
  return (
    <div className="mx-auto max-w-2xl flex flex-col gap-6">
      <div>
        <h2 className="text-xl font-semibold">Upload Documents</h2>
        <p className="text-sm text-muted-foreground">PDF, DOCX, and TXT files up to 500MB</p>
      </div>
      <UploadZone />
    </div>
  );
}
