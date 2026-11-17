export default function Home() {
  return (
    <main className="flex min-h-screen items-center justify-center">
      <div className="text-center">
        <h1 className="text-2xl font-semibold">TestHarbor</h1>
        <p className="mt-2 text-muted-foreground">
          Backend is up. API docs: <a className="text-primary underline" href="/docs">/docs</a>
        </p>
      </div>
    </main>
  );
}
