import { NextResponse } from "next/server";
import Groq from "groq-sdk";

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const { mode, prompt, context, systemInstruction, customKey, model } = body;

    const apiKey = (customKey || process.env.GROQ_API_KEY || "").trim();
    if (!apiKey) {
      return NextResponse.json(
        { error: "Groq API key not found. Please provide an API key in settings or set GROQ_API_KEY." },
        { status: 401 }
      );
    }

    const groq = new Groq({ apiKey });
    const targetModel = model || process.env.GROQ_MODEL || "llama-3.3-70b-versatile";

    if (mode === "explain") {
      const messages: any[] = [
        {
          role: "system",
          content:
            "You are GapFinder AI, a rigorous evidence-grounded study tutor. Answer strictly from the provided context. If the answer is not present in the notes, respond EXACTLY: 'Not found in your uploaded material.'"
        },
        {
          role: "user",
          content: `QUESTION / TOPIC: ${prompt}\n\nRETRIEVED NOTES CONTEXT:\n${context}\n\nSTRICT RULES:\n1. Answer ONLY from the retrieved notes above.\n2. Do NOT use outside general knowledge.\n3. If the retrieved notes are insufficient to answer, respond EXACTLY: 'Not found in your uploaded material.'\n4. If answering, write 3 concise bullet points citing the source tag.`
        }
      ];

      const completion = await groq.chat.completions.create({
        messages,
        model: targetModel,
        temperature: 0.1,
        max_tokens: 600
      });

      const answer = completion.choices[0]?.message?.content || "Not found in your uploaded material.";
      return NextResponse.json({ answer });
    }

    if (mode === "quiz") {
      const messages: any[] = [
        {
          role: "system",
          content:
            "You are an expert exam diagnostician. You must output ONLY a valid JSON array of 4 multiple-choice questions grounded in the provided notes."
        },
        {
          role: "user",
          content: `${prompt}\n\nRETRIEVED CHUNKS:\n${context}\n\nRULES:\n- Return ONLY a valid JSON array of 4 objects.\n- Keys: id (number), topic (string), question (string), options (array of 4 strings), answer (string matching one option), citation (string), explanation (string).`
        }
      ];

      const completion = await groq.chat.completions.create({
        messages,
        model: targetModel,
        temperature: 0.3,
        max_tokens: 1200
      });

      const raw = completion.choices[0]?.message?.content || "";
      let parsed;
      try {
        const clean = raw.replace(/```(?:json)?/g, "").replace(/```/g, "").trim();
        parsed = JSON.parse(clean);
      } catch (e) {
        return NextResponse.json({ error: "Failed to parse JSON from model output", raw });
      }

      return NextResponse.json({ quiz: parsed });
    }

    // Default prompt completion
    const completion = await groq.chat.completions.create({
      messages: [
        { role: "system", content: systemInstruction || "You are GapFinder AI tutor." },
        { role: "user", content: prompt }
      ],
      model: targetModel,
      temperature: 0.2,
      max_tokens: 800
    });

    return NextResponse.json({ result: completion.choices[0]?.message?.content || "" });
  } catch (err: any) {
    return NextResponse.json(
      { error: err?.message || "Internal server error communicating with Groq" },
      { status: 500 }
    );
  }
}
