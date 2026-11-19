package org.madlink.preview;
import android.app.Activity;
import android.os.Bundle;
import android.widget.TextView;
public final class MainActivity extends Activity {
 static { System.loadLibrary("smoke"); }
 public static native int runSmoke();
 @Override public void onCreate(Bundle b) { super.onCreate(b); TextView v=new TextView(this); v.setText(runSmoke()==0 ? "PASS synthetic lifecycle" : "FAIL synthetic lifecycle"); setContentView(v); }
}
