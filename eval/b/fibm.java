
class fibm {
  public static void main(String[] args) {
      int n = Integer.parseInt(args[0]);
      int times = Integer.parseInt(args[1]);
      int result = -1;
      for (int i=0; i<times; i++) {
          result = fib(n);
      }
      System.out.println(result);
  }

  public static int fib(int n) {
      int array[] = new int[n+1];
      array[0] = array[1] = 1;
      for (int i=2; i<n+1; i++) {
          array[i] = array[i-1] + array[i-2];
      }
      return array[n];
  }
}

