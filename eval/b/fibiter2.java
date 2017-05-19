
class fibiter2 {
  public static void main(String[] args) {
      System.out.println(fib(Double.parseDouble(args[0])));
  }

  public static double fib(double n) {
      if (n < 2.0) return 1.0;
      else return fib(n - 1.0) + fib(n - 2.0);
  }
}

