import { useState } from "react";
import ReactMarkdown from "react-markdown";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "./dialog";
import { ScrollArea } from "./scroll-area";
import { Spinner } from "./spinner";
import { api, enc, ApiError } from "../../lib/api";

interface DocResponse {
  name: string;
  content: string;
}

/** Fetches a whitelisted docs/*.md file from the backend and renders it as
    markdown in a dialog, so a doc reference in the UI can be read in place
    instead of sending the user to dig through the repo. */
export function DocDialog({
  doc,
  trigger,
}: {
  doc: string;
  trigger: React.ReactNode;
}) {
  const [content, setContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = () => {
    if (content || loading) return;
    setLoading(true);
    setError(null);
    api<DocResponse>(`/api/docs/${enc(doc)}`)
      .then((res) => setContent(res.content))
      .catch((err: unknown) =>
        setError(err instanceof ApiError ? err.message : "Failed to load doc."),
      )
      .finally(() => setLoading(false));
  };

  return (
    <Dialog onOpenChange={(open) => open && load()}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="flex h-[min(85vh,42rem)] w-[min(92vw,48rem)] flex-col overflow-hidden">
        <DialogHeader>
          <DialogTitle>
            <code>{doc}</code>
          </DialogTitle>
        </DialogHeader>
        <ScrollArea className="mt-2 flex-1">
          {loading && <Spinner label={`Loading ${doc}…`} />}
          {error && <p className="text-sm text-[var(--err)]">{error}</p>}
          {content && (
            <div
              className="pr-4 text-sm [&_h1]:mt-4 [&_h2]:mt-4 [&_h3]:mt-3
                [&_li]:ml-5 [&_ol]:my-2 [&_ol]:list-decimal [&_p]:my-2
                [&_pre]:my-2 [&_pre]:overflow-x-auto [&_pre]:rounded-md
                [&_pre]:bg-[var(--surface-2)] [&_pre]:p-3
                [&_ul]:my-2 [&_ul]:list-disc"
            >
              <ReactMarkdown>{content}</ReactMarkdown>
            </div>
          )}
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
