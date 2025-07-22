// supabase/functions/telegram-bot/index.ts
import { serve } from "https://deno.land/std@0.224.0/http/server.ts";

const TELEGRAM_BOT_TOKEN = "8189696717:AAEHt1aEPosYYsBaxPxAfaKaNwtA19hu2xs"; // 🔁 替换为真实值
const TELEGRAM_API = `https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}`;

serve(async (req: Request): Promise<Response> => {
  if (req.method !== "POST") {
    return new Response("Method Not Allowed", { status: 405 });
  }

  try {
    const body = await req.json();
    const chatId = body.message?.chat?.id;
    const text = body.message?.text;

    console.log("Received Telegram message:", text);

    if (chatId && text) {
      const reply = `你刚才说了：${text}`;

      await fetch(`${TELEGRAM_API}/sendMessage`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          chat_id: chatId,
          text: reply,
        }),
      });
    }

    return new Response("ok", { status: 200 });
  } catch (error) {
    console.error("Error handling webhook:", error);
    return new Response("error", { status: 500 });
  }
});
