// User service — wraps a single Prisma query
import { db } from "@/lib/db";

interface IUserService {
  getUserById(id: string): Promise<{ id: string; email: string; name: string } | null>;
}

class UserService implements IUserService {
  async getUserById(id: string) {
    return db.user.findUnique({
      where: { id },
      select: { id: true, email: true, name: true },
    });
  }
}

const userServiceFactory = () => new UserService();

export const userService: IUserService = userServiceFactory();
