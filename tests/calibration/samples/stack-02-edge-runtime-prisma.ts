import { db } from "@/lib/db";
import { NextRequest, NextResponse } from "next/server";

export const runtime = "edge";

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const query = searchParams.get("q") ?? "";

  const results = await db.post.findMany({
    where: {
      OR: [
        { title: { contains: query, mode: "insensitive" } },
        { content: { contains: query, mode: "insensitive" } },
      ],
    },
    select: { id: true, title: true, excerpt: true, createdAt: true },
    take: 20,
  });

  return NextResponse.json({ results });
}
