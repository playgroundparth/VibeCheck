import OpenAI from "openai";
import { auth } from "@/lib/auth";
import { NextRequest, NextResponse } from "next/server";

const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });

export async function POST(req: NextRequest) {
  const session = await auth();
  if (!session) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { prompt } = await req.json();

  const completion = await openai.chat.completions.create({
    model: "gpt-4o",
    messages: [
      { role: "system", content: "You are a helpful assistant for our app." },
      { role: "user", content: prompt },
    ],
  });

  return NextResponse.json({
    response: completion.choices[0].message.content,
  });
}
