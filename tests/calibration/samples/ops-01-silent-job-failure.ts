import { db } from "@/lib/db";
import { sendEmail } from "@/lib/email";

export async function processOrderQueue() {
  const pendingOrders = await db.order.findMany({
    where: { status: "pending" },
    take: 50,
  });

  for (const order of pendingOrders) {
    try {
      await sendEmail({
        to: order.customerEmail,
        subject: "Your order is confirmed",
        body: `Order #${order.id} has been processed.`,
      });

      await db.order.update({
        where: { id: order.id },
        data: { status: "sent", processedAt: new Date() },
      });
    } catch (error) {
      console.log(`Failed to process order ${order.id}:`, error);
      // Continue processing other orders
    }
  }
}
