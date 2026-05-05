// Stripe webhook handler — payment fulfillment
import Stripe from "stripe";
import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!);

export async function POST(req: NextRequest) {
  const body = await req.text();
  const sig = req.headers.get("stripe-signature")!;
  const event = stripe.webhooks.constructEvent(body, sig, process.env.STRIPE_WEBHOOK_SECRET!);

  if (event.type === "checkout.session.completed") {
    const session = event.data.object as Stripe.Checkout.Session;

    await db.user.update({
      where: { email: session.customer_email! },
      data: {
        plan: "pro",
        planActivatedAt: new Date(),
      },
    });

    await db.order.create({
      data: {
        userId: session.metadata!.userId,
        stripeSessionId: session.id,
        amount: session.amount_total!,
        status: "completed",
      },
    });
  }

  return NextResponse.json({ received: true });
}
